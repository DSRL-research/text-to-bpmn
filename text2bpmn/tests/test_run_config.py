import dataclasses
import random

import pytest

from text2bpmn.run_config import RunConfig, parse_known


def test_apply_seeds_are_reproducible():
    first = [random.random() for _ in range(3)] if RunConfig(seed=7).apply() else None
    second = [random.random() for _ in range(3)] if RunConfig(seed=7).apply() else None
    assert first == second
    other = [random.random() for _ in range(3)] if RunConfig(seed=8).apply() else None
    assert other != first


def test_command_line_overrides_defaults():
    config = parse_known(["--seed", "13", "--temperature", "0.7", "--model", "ollama/other:latest",
                          "--guardrail-mode", "entity_2", "--unrelated", "x"])
    assert (config.seed, config.temperature, config.llm_model, config.guardrail_mode) == \
           (13, 0.7, "ollama/other:latest", "entity_2")


def test_description_records_what_produced_the_run():
    record = RunConfig(seed=3, temperature=0.0, api_base="http://localhost:9").describe()
    assert record["config"]["seed"] == 3 and record["config"]["temperature"] == 0.0
    assert record["llm"]["reachable"] is False  # nothing listens there; recorded, not raised
    assert record["packages"]["dspy"] and record["packages"]["transformers"]
    assert len(record["code"]["commit"]) == 40 and record["run_at"].endswith("+00:00")


def test_a_relation_call_has_a_deadline():
    """A server that accepts the connection and never replies once held a
    45-document evaluation for half an hour with no diagnostic. The timeout
    turns that into a parse failure, which the C7 log counts."""
    from text2bpmn.run_config import RunConfig, parse_known
    assert RunConfig().llm_timeout == 120
    assert parse_known(["--llm-timeout", "30"]).llm_timeout == 30


def test_the_record_names_the_tag_the_code_is_at():
    record = RunConfig(api_base="http://localhost:9").describe()
    assert record["code"]["describe"], "git describe: the tag, or the commit past it"


def test_the_cache_is_off_unless_asked_for():
    assert RunConfig().llm_cache is False
    assert parse_known(["--llm-cache"]).llm_cache is True


def ollama_record(**llm):
    return {"llm": {"name": "deepseek-10k:latest", **llm}}


def test_a_run_without_its_model_is_refused():
    config = RunConfig(llm_model="ollama/deepseek-10k:latest", api_base="http://localhost:9")
    with pytest.raises(RuntimeError, match="not reachable"):
        config.require_llm(ollama_record(reachable=False, error="refused"))
    with pytest.raises(RuntimeError, match="no digest"):
        config.require_llm(ollama_record(reachable=True, digest=None))
    config.require_llm(ollama_record(reachable=True, digest="0882bee73555"))  # the normal case


def test_an_openai_server_must_be_serving_the_model():
    config = RunConfig(llm_model="hosted_vllm/Qwen/Qwen3.5-9B", api_base="http://localhost:9/v1")
    record = {"llm": {"reachable": True, "api": "openai", "served_models": ["other"],
                      "serving_this_model": False, "digest": None}}
    with pytest.raises(RuntimeError, match="not served"):
        config.require_llm(record)
    record["llm"].update(served_models=["Qwen/Qwen3.5-9B"], serving_this_model=True)
    config.require_llm(record)


def test_the_no_llm_control_is_an_explicit_choice():
    assert parse_known(["--allow-no-llm"]).allow_no_llm is True
    RunConfig(allow_no_llm=True).require_llm(ollama_record(reachable=False))


def test_the_pipeline_refuses_to_start_without_its_llm():
    """The committed case outputs of 2026-10-02 were produced this way, from
    DSPy's cache, with the server down and no digest recorded."""
    from text2bpmn.finder3 import BPMNHybridExtractor
    with pytest.raises(RuntimeError, match="not reachable"):
        BPMNHybridExtractor(config=RunConfig(api_base="http://127.0.0.1:1"), ner_model_path=None)
    allowed = BPMNHybridExtractor(config=RunConfig(api_base="http://127.0.0.1:1", allow_no_llm=True),
                                  ner_model_path=None)
    assert allowed.run_record["llm"]["reachable"] is False


def test_the_benchmark_and_the_pipeline_build_the_same_client():
    """benchmark_relations used to hard-code the API key and ignore thinking
    and constrained answers, so a vLLM run could not match the pipeline's."""
    from text2bpmn.finder3 import build_lm, relation_schema
    lm = build_lm(RunConfig(llm_model="hosted_vllm/qwen3", api_base="http://localhost:8000/v1",
                            api_key="EMPTY", disable_thinking=True, constrained_output=True, llm_timeout=90,
                            reasoning_max_chars=1500, max_tokens=1024))
    assert lm.model == "hosted_vllm/qwen3" and lm.cache is False
    assert lm.kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert lm.kwargs["response_format"]["json_schema"]["schema"] == relation_schema(1500)
    assert relation_schema(1500)["properties"]["reasoning"]["maxLength"] == 1500
    assert (lm.kwargs["api_key"], lm.kwargs["timeout"], lm.kwargs["temperature"]) == ("EMPTY", 90, 0.0)
    assert lm.kwargs["max_tokens"] == 1024


def test_the_new_settings_come_from_the_command_line():
    config = parse_known(["--reasoning-max-chars", "800", "--max-tokens", "512"])
    assert (config.reasoning_max_chars, config.max_tokens) == (800, 512)
    assert parse_known([]).max_tokens == 1024
    assert parse_known(["--max-tokens", "0"]).max_tokens == 0


def test_a_run_without_flags_uses_the_release_runs_settings():
    """The paper's settings are the defaults: every field of the release run's
    recorded config (runs/final-3/cases/run_record.json) is what a command line
    without flags gives."""
    import json
    from pathlib import Path
    record = json.loads((Path(__file__).resolve().parents[2]
                         / "runs/final-3/cases/run_record.json").read_text())["config"]
    config = parse_known([])
    assert {k: getattr(config, k) for k in record} == record
    assert (config.relation_mode, config.disable_thinking, config.constrained_output, config.max_tokens,
            config.temperature, config.llm_model) == ("decisions4", True, True, 1024, 0.0,
                                                      "hosted_vllm/Qwen/Qwen3.5-27B-FP8")


def test_each_new_default_can_be_switched_back():
    config = parse_known(["--thinking", "--no-constrained-output", "--max-tokens", "0"])
    assert (config.disable_thinking, config.constrained_output, config.max_tokens) == (False, False, 0)


def _fake_server(monkeypatch, content):
    """Replace litellm's completion with one that records each request."""
    import litellm
    import dspy.clients.lm as dspy_lm

    requests = []

    def completion(**kwargs):
        requests.append(kwargs)
        return litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            model=kwargs["model"], usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    monkeypatch.setattr(dspy_lm.litellm, "completion", completion)
    return requests


def _ask(config):
    import dspy
    from text2bpmn.finder3 import BPMNRelationPredictor, configure_dspy
    from text2bpmn.prompts import load_demonstrations

    saved = dspy.settings.lm, dspy.settings.adapter
    try:
        configure_dspy(config)
        predictor = BPMNRelationPredictor(config.prompt)
        predictor.prog.predict.demos = load_demonstrations()
        return predictor(context="The clerk checks the form. Then the clerk files it.",
                         node_A="checks the form", node_B="files it")
    finally:
        dspy.settings.configure(lm=saved[0], adapter=saved[1])


VLLM = dict(llm_model="hosted_vllm/Qwen/Qwen3.5-27B-FP8", api_base="http://localhost:11434/v1",
            api_key="EMPTY", disable_thinking=True)


def test_constrained_output_makes_one_call_per_pair_and_keeps_the_schema(monkeypatch):
    """DSPy's default adapter could not read the JSON the schema forces, so it
    discarded every answer and asked again in plain JSON mode: two calls per
    pair, and the answer kept was the unconstrained one (2026-11-04)."""
    import json
    from text2bpmn.finder3 import relation_schema

    requests = _fake_server(monkeypatch, json.dumps({"reasoning": "B comes after A.", "relation": "SEQUENCE"}))
    answer = _ask(RunConfig(**VLLM, constrained_output=True, reasoning_max_chars=2000))
    assert answer.relation == "SEQUENCE" and answer.reasoning == "B comes after A."
    assert len(requests) == 1
    assert requests[0]["response_format"]["json_schema"]["schema"] == relation_schema(2000)


def test_a_constrained_reply_that_does_not_parse_is_a_failure_not_a_second_call(monkeypatch):
    import json
    from dspy.utils.exceptions import AdapterParseError

    requests = _fake_server(monkeypatch, json.dumps({"reasoning": "never answers"}))
    with pytest.raises(AdapterParseError):
        _ask(RunConfig(**VLLM, constrained_output=True))
    assert len(requests) == 1


def test_free_text_answers_still_use_one_call(monkeypatch):
    requests = _fake_server(monkeypatch, "[[ ## reasoning ## ]]\nB comes after A.\n\n"
                                         "[[ ## relation ## ]]\nSEQUENCE\n\n[[ ## completed ## ]]")
    answer = _ask(RunConfig(**VLLM, constrained_output=False))
    assert answer.relation == "SEQUENCE" and len(requests) == 1
    assert "response_format" not in requests[0]


def test_run_final_hands_every_llm_setting_to_the_benchmark(monkeypatch, tmp_path):
    """Runs 1 and 2 run benchmark_relations in a subprocess; a setting that is
    not on its command line silently falls back to the default there."""
    import subprocess
    from text2bpmn import run_final

    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        (tmp_path / "benchmark_run.json").write_text("{}")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_final.subprocess, "run", fake_run)
    config = RunConfig(**VLLM, constrained_output=True, reasoning_max_chars=1500, max_tokens=1024,
                       llm_timeout=90, model_revision="0123abcd")
    run_final.benchmark("corrected_302", config, tmp_path, dry=False)
    parsed = parse_known(seen["command"][3:])  # after python -m text2bpmn.benchmark_relations
    for field in ("llm_model", "api_base", "api_key", "prompt", "temperature", "llm_timeout",
                  "constrained_output", "disable_thinking", "reasoning_max_chars", "max_tokens",
                  "model_revision"):
        assert getattr(parsed, field) == getattr(config, field), field
    # settings switched off must reach the benchmark switched off, not as its defaults
    off = dataclasses.replace(config, constrained_output=False, disable_thinking=False, max_tokens=None)
    run_final.benchmark("corrected_302", off, tmp_path, dry=False)
    parsed = parse_known(seen["command"][3:])
    assert (parsed.constrained_output, parsed.disable_thinking, parsed.max_tokens) == (False, False, 0)


QWEN_REVISION = "97f5941bf617e31c5e237364a8602ce3f03a551a"


def test_the_default_llm_is_the_final_runs_vllm_model_not_ollama():
    config = RunConfig()
    assert config.llm_model == "hosted_vllm/Qwen/Qwen3.5-27B-FP8" and config.backend == "openai"
    assert config.api_base == "http://localhost:11434/v1" and config.api_key == "EMPTY"
    assert "ollama" not in config.llm_model and "deepseek" not in config.llm_model
    # Ollama is still there when asked for by name
    assert RunConfig(llm_model="ollama/deepseek-10k:latest").backend == "ollama"


def test_the_record_keeps_the_model_revision():
    """The release runs served Qwen3.5-27B-FP8 as `main` and recorded no
    revision; a record now says which one it declares, and from where."""
    llm = RunConfig(api_base="http://localhost:9/v1").describe()["llm"]
    assert (llm["revision"], llm["revision_from"], llm["revision_checked"]) == \
           (QWEN_REVISION, "run_config.MODEL_REVISIONS", False)
    assert llm["reachable"] is False  # recorded whether or not the server answers
    chosen = parse_known(["--model-revision", "0123abcd", "--api-base", "http://localhost:9/v1"])
    assert chosen.model_revision == "0123abcd"
    assert chosen.llm_identity()["revision"] == "0123abcd"
    assert chosen.llm_identity()["revision_from"] == "--model-revision"
    other = RunConfig(llm_model="hosted_vllm/Qwen/Qwen3.5-9B", api_base="http://localhost:9/v1")
    assert other.llm_identity()["revision"] is None  # no revision is invented for another model


def test_run_final_writes_the_revision_into_each_run_record(tmp_path):
    import json
    from text2bpmn import run_final

    config = RunConfig(api_base="http://localhost:9/v1")
    runners = {"probe": (lambda name, config, out, dry: {}, "corrected", False)}
    run_final.run_experiments(["probe"], runners, config, {"describe": "x"}, tmp_path, dry_run=False)
    record = json.loads((tmp_path / "probe" / "run_record.json").read_text(encoding="utf-8"))
    assert record["llm"]["revision"] == QWEN_REVISION
    assert record["config"]["model_revision"] is None  # the default, resolved in llm.revision
