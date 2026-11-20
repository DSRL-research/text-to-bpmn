"""The goods dispatch concurrency question as the release run sent it, rebuilt from the saved run.

    python3 -m text2bpmn.checks.concurrency_prompt
        # -> runs/checks/final-3/open_analyses/concurrency_prompt_goods_dispatch.{md,json}

The run does not save prompts: its log and decisions.json keep only the
question's node_A / node_B and the labels answered (finder3._ask_parallel). The
prompt is a pure function of saved inputs, so it is rebuilt here twice, and the
two must agree:

1. **From the saved files.** decisions.ask_parallel_llm sends two messages:
   system = decisions.INSTRUCTIONS_PARALLEL; user = decisions.parallel_question
   (context, cue, steps, name, lanes). The context is the text the recogniser
   read (the log's "Coref Resolved" line, which finder3.process_text passes to
   the relation stage); the cue and the steps are the entities of
   extraction.json whose names decisions.json lists, in that order; each
   step's lane is its element's lane in extraction.json's structured_data (the
   graph as the relation stage built it, before the Validation Layer).
2. **By replay.** The release code runs again on the spans the log printed
   ("Split Entities"), injected as finder3.process_text allows, each decision
   question answered with its logged labels, and the concurrency question
   answered through decisions.ask_parallel_llm itself with a stand-in client
   that records the messages and request options and replies with the logged
   labels. No LLM is called, and no file is written (ontology_out is empty).
   The replayed graph must equal the saved one, flow for flow.
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

from text2bpmn import decisions

CASE = Path("runs/final-3/cases/goods_dispatch")
OUT = Path("runs/checks/final-3/open_analyses/concurrency_prompt_goods_dispatch")


def saved():
    log = (CASE / "log.txt").read_text(encoding="utf-8")
    extraction = json.loads((CASE / "extraction.json").read_text(encoding="utf-8"))
    asked = json.loads((CASE / "decisions.json").read_text(encoding="utf-8"))["decisions"]
    context = log.split("(Debug) Coref Resolved: ", 1)[1].split("\n", 1)[0]
    spans = ast.literal_eval(log.split("--- Split Entities ---\n", 1)[1].split("\n", 1)[0])
    return log, extraction, asked, context, spans


def from_files():
    _, extraction, asked, context, _ = saved()
    question = next(q for q in asked if q["node_A"].startswith("parallel: "))
    cue_name, step_names = question["node_A"][len("parallel: "):], question["node_B"].split(" | ")
    used = extraction["entities_used"]
    cue = next(e for e in used if e["label"] == "AND Gateway" and e["name"] == cue_name)
    steps = []
    for step_name in step_names:  # each name is one task's
        found = [e for e in used if e["type"] == "task" and e["name"] == step_name]
        assert len(found) == 1, step_name
        steps.append(found[0])
    lane = {e["id"]: e["lane"] for e in extraction["structured_data"]["elements"]}
    lanes = [lane[s["id"]] for s in steps]
    entity = lambda e: {"start": e["start"], "clean_name": e["name"], "word": e["name"]}  # noqa: E731
    name = lambda e: e.get("clean_name") or e["word"]  # noqa: E731  finder3._relation_text
    config = extraction["run_config"]["config"]
    messages = [{"role": "system", "content": decisions.INSTRUCTIONS_PARALLEL},
                {"role": "user", "content": decisions.parallel_question(context, entity(cue),
                                                                        [entity(s) for s in steps], name, lanes)}]
    schema = decisions.parallel_schema(len(steps), config["reasoning_max_chars"])
    return {"question": question, "cue": cue, "steps": steps, "lanes": lanes, "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": "parallel", "schema": schema}},
            "config": config}


def by_replay():
    import contextlib
    import io

    from text2bpmn import pet_strict as ps
    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    _, extraction, asked, context, spans = saved()
    run = extraction["run_config"]["config"]
    config = RunConfig(relation_mode=run["relation_mode"], allow_no_llm=True, api_base="http://127.0.0.1:1",
                       llm_timeout=5, ontology_out="")
    with contextlib.redirect_stdout(io.StringIO()):
        x = BPMNHybridExtractor(config=config, ner_model_path=None)
    logged = {(q["node_A"], q["node_B"]): q["label"].split() for q in asked if q.get("source") == "llm"}
    sent = []

    def ask_decision(ctx, decision, steps, lanes, kinds=None):
        pair = (x._relation_text(decision),
                " | ".join(("decision: " if k == "decision" else "") + x._relation_text(s)
                           for s, k in zip(steps, kinds or ["step"] * len(steps))))
        return logged.get(pair)

    def ask_parallel(ctx, cue, steps, lanes):
        labels = logged[("parallel: " + x._relation_text(cue), " | ".join(x._relation_text(s) for s in steps))]

        def client(messages, **options):  # stands in for dspy.settings.lm
            sent.append({"messages": messages, "options": options, "lanes": list(lanes)})
            return [json.dumps({"reasoning": "", **{f"step_{k}": v for k, v in enumerate(labels, 1)}})]

        cfg = SimpleNamespace(constrained_output=run["constrained_output"],
                              reasoning_max_chars=run["reasoning_max_chars"])
        return decisions.ask_parallel_llm(client, ctx, cue, steps, x._relation_text, lanes, cfg)

    x._ask_decision, x._ask_parallel = ask_decision, ask_parallel
    injected = [{"start": s["start"], "end": s["end"], "label": s["entity_group"], "score": s["score"]}
                for s in spans]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = x.process_text(context, entities={"text": context, "spans": injected, "source": "replay"})
    same = ps._span_flows(result) == ps._span_flows(extraction)
    return {"sent": sent, "same_graph": same}


def analyse():
    files = from_files()
    replay = by_replay()
    assert replay["same_graph"], "the replay does not rebuild the saved graph"
    assert len(replay["sent"]) == 1
    sent = replay["sent"][0]
    assert sent["messages"] == files["messages"], "the two reconstructions differ"
    assert sent["options"] == {"response_format": files["response_format"]}
    c = files["config"]
    return {"case": str(CASE), "question_logged": files["question"],
            "messages": files["messages"], "response_format": files["response_format"],
            "lanes_of_the_steps": files["lanes"],
            "lanes_in_the_user_message": all(f"({lane})" in files["messages"][1]["content"]
                                             for lane in files["lanes"]),
            "request_settings": {"model": c["llm_model"], "temperature": c["temperature"], "seed": c["seed"],
                                 "max_tokens": c["max_tokens"],
                                 "extra_body": {"chat_template_kwargs": {"enable_thinking": not c["disable_thinking"]}}},
            "replay": {"same_graph_as_saved": replay["same_graph"], "messages_equal": True},
            "code": {"messages": "text2bpmn/decisions.py ask_parallel_llm (system INSTRUCTIONS_PARALLEL, "
                                 "user parallel_question)",
                     "lanes": "text2bpmn/decisions.py parallel_plan passes nodes[j][1]['lane'] for each window "
                              "step; parallel_question appends ' (lane)' unless the lane is empty or Main Process"}}


def markdown(r):
    fence = "```"
    lines = ["# The goods dispatch concurrency question, as the release run sent it", "",
             "Generated by `text2bpmn/checks/concurrency_prompt.py` from `runs/final-3/cases/goods_dispatch` "
             "(log.txt, extraction.json, decisions.json); rebuilt from the saved files and by replay, the two equal, "
             "and the replay rebuilds the saved graph.", "",
             f"Logged question: node_A `{r['question_logged']['node_A']}`, node_B `{r['question_logged']['node_B']}`, "
             f"answer `{r['question_logged']['label']}`.", "",
             f"Lanes of the steps: {r['lanes_of_the_steps']}; shown in the user message: "
             f"{'yes' if r['lanes_in_the_user_message'] else 'no'}.", "",
             "## System message", "", fence, r["messages"][0]["content"], fence, "",
             "## User message", "", fence, r["messages"][1]["content"], fence, "",
             "## Request options", "", fence + "json",
             json.dumps({"response_format": r["response_format"], **r["request_settings"]}, indent=1), fence, ""]
    return "\n".join(lines)


def main():
    result = analyse()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    text = markdown(result)
    OUT.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
