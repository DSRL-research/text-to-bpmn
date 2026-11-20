"""Reproducible run configuration (ticket C9).

Every run seeds the random sources explicitly, fixes the LLM temperature, and
records what produced it: the seed and temperature, the LLM name with the exact
model digest reported by the server (Ollama) or the model revision the run
declares (vLLM reports none), the NER checkpoint, the package versions and the
commit the code was at. `describe()` returns that record, which the
pipeline and the benchmark write into their output, so an experiment can be
repeated from its own log.
"""
import argparse
import importlib.metadata as metadata
import json
import random
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from text2bpmn.prompts import DEFAULT_PROMPT, PROMPTS

# The LLM of the final method's runs (revision-final-3): Qwen3.5-27B-FP8 served
# by vLLM's OpenAI-compatible API on port 11434, as in runs/final-3/vllm.log.
# Until 2026-11-17 the default was "ollama/deepseek-10k:latest" on Ollama's root
# http://localhost:11434, the model behind the submitted numbers.
DEFAULT_LLM = "hosted_vllm/Qwen/Qwen3.5-27B-FP8"
DEFAULT_API_BASE = "http://localhost:11434/v1"
# The Hugging Face revision of each model whose runs this project reports. The
# release runs served Qwen3.5-27B-FP8 as "main" (runs/final-3/vllm.log:
# revision=main), which was this commit then: its tokenizer reproduces the
# logged prompt tokens exactly (text2bpmn/checks/token_usage.py). Serve it
# with `vllm serve ... --revision` and this value (README.md).
MODEL_REVISIONS = {"Qwen/Qwen3.5-27B-FP8": "97f5941bf617e31c5e237364a8602ce3f03a551a"}
PACKAGES = ("dspy", "litellm", "transformers", "torch", "spacy", "scikit-learn", "pm4py")


@dataclass
class RunConfig:
    seed: int = 0
    temperature: float = 0.0
    llm_model: str = DEFAULT_LLM
    api_base: str = DEFAULT_API_BASE
    # Any OpenAI-compatible server wants a key and vLLM ignores its value;
    # it is recorded like everything else, so never put a real secret here.
    api_key: str = "EMPTY"
    # The model's revision on the Hugging Face Hub, as the server was started
    # with it (vllm serve --revision). Empty: the revision in MODEL_REVISIONS
    # for this model, if it has one. Neither server API reports a revision, so
    # the run record keeps it as declared, not as checked (llm_identity()).
    model_revision: str | None = None
    few_shot_k: int = 10
    # The relation classifier's instructions, by name from text2bpmn/prompts.py.
    # "published" and "table3" reproduce the published numbers.
    prompt: str = DEFAULT_PROMPT
    # Seconds to wait for one relation answer. Without a limit a server that
    # accepts the connection and never replies stalls the whole run: one such
    # request held a 45-document evaluation for half an hour with no
    # diagnostic. A timeout makes it a parse failure instead, which ticket C7's
    # log already counts and reports.
    llm_timeout: int = 120
    # Force the answer field to one of the five labels with a JSON schema the
    # server decodes against. On by default since 2026-11-17, as in the final
    # method's runs (revision-final-3, runs/final-3/cases/run_record.json); the
    # submitted numbers (revision-final) were produced without it, which
    # --no-constrained-output restores. Until 2026-11-04 the flag made two calls
    # per pair and kept the answer of the unconstrained second one.
    constrained_output: bool = True
    # With constrained_output, the schema closes the reasoning string at this
    # many characters, after which the server must emit the answer. Without a
    # cap Qwen3.5-27B (thinking off) wrote ~10,000 characters for one pair and
    # timed out on 11 of 123 calls in one PET document (2026-11-04).
    reasoning_max_chars: int = 2000
    # Tokens one reply may generate; None or 0 leaves it to the server. A
    # backstop for a server that ignores the schema's length limit: the reply is
    # then cut and counted as failed rather than running into the timeout. 1024
    # since 2026-11-17, as in the final method's runs.
    max_tokens: int | None = 1024
    # Turn a hybrid model's thinking off. Qwen3 and Qwen3.5 reason by default
    # and are then the same problem deepseek-10k was: ~12,500 characters of
    # deliberation per pair and an answer field that never arrives. vLLM takes
    # it as chat_template_kwargs; Ollama ignores it, which is harmless. On by
    # default since 2026-11-17, as in the final method's runs; --thinking
    # leaves the model's own default.
    disable_thinking: bool = True
    # Spend a second call on the pairs that earn it: reason unconstrained, then
    # decode only the answer against the five labels. text2bpmn/two_phase.py
    # decides which pairs those are, from where the failures actually clustered.
    two_phase: bool = False
    # DSPy's request cache. Off by default: with it on, a run whose prompts are
    # unchanged replays stored answers, and the committed case outputs of
    # 2026-10-02 came from the cache while the server was down.
    llm_cache: bool = False
    # A run stops when the LLM server cannot be reached, or reports no digest
    # for the model. Only the no-LLM control,
    # which deliberately points at a closed port, sets this.
    allow_no_llm: bool = False
    guardrail_mode: str = "entity_1"
    parallel_detection: str = "all"  # all | cues | off; see text2bpmn/cues.py
    # Three guards on which PARALLEL answers may form a block. Each is separate
    # so its effect can be reported on its own.
    parallel_mutual: bool = False       # both directions must answer PARALLEL
    parallel_require_cue: bool = False  # the text must carry a concurrency cue
    parallel_anchor_guard: bool = False # a step already following another cannot anchor
    # How the LLM is asked about structure. The default since revision-final-3
    # (2026-11-12) is "decisions4", relation idea 3: one question per decision
    # about the steps after it and one per concurrency word, with the soundness
    # gate (text2bpmn/decisions.py, text2bpmn/soundness_gate.py); from
    # revision-final-2 to then it was "decisions3", idea 1c. The comparisons
    # that chose them are Section 4.5's (Table 8). "pairs" is the
    # relation classifier on every element and the three after it (the method
    # as submitted, and every run up to revision-final-gliner), or
    # "decisions", one question per decision about the steps after it
    # (text2bpmn/decisions.py, relation idea 1), or "decisions2", the same with
    # later mentions of one decision recognised as its other cases (idea 1b),
    # "decisions3", 1b with parallel-gateway words left out (idea 1c), or
    # "decisions4", 1c with one question per parallel-gateway word (idea 3), or
    # "pairs2", the pair questions with a NONE answer, asked only of neighbours
    # and of pairs with a gateway (idea 2; prompt corrected_none).
    relation_mode: str = "decisions4"
    ontology_file: str = "BPMNbasedOntologyV1_2.owl"  # BPMN 2.0 ontology to populate
    ontology_out: str = ""  # where to save the populated copy; empty disables the step
    ner_model_path: str = ""

    def apply(self):
        """Seed every random source the pipeline can reach."""
        random.seed(self.seed)
        try:
            import numpy
            numpy.random.seed(self.seed)
        except ImportError:
            pass
        try:
            import torch
            torch.manual_seed(self.seed)
            torch.cuda.manual_seed_all(self.seed)
        except ImportError:
            pass
        return self

    @property
    def backend(self):
        """Which server this configuration talks to, from the model prefix.

        `ollama/NAME` is Ollama's own API; `hosted_vllm/NAME` and `openai/NAME`
        are the OpenAI-compatible API that vLLM serves, where the model is
        whatever was loaded at startup and there is nothing to pull.
        """
        prefix = self.llm_model.split("/", 1)[0] if "/" in self.llm_model else ""
        return "ollama" if prefix == "ollama" else "openai"

    @property
    def revision(self):
        """The model revision this run declares, and where it comes from."""
        if self.model_revision:
            return self.model_revision, "--model-revision"
        name = self.llm_model.split("/", 1)[-1]
        if name in MODEL_REVISIONS:
            return MODEL_REVISIONS[name], "run_config.MODEL_REVISIONS"
        return None, None

    def llm_identity(self):
        """What the LLM server says it is serving under this name, with the
        model revision the run declares for it."""
        revision, source = self.revision
        return {**self._server_identity(),
                "revision": revision, "revision_from": source, "revision_checked": False}

    def _server_identity(self):
        if self.backend == "openai":
            return self._openai_identity()
        name = self.llm_model.split("/", 1)[-1]
        request = urllib.request.Request(f"{self.api_base}/api/show",
                                         data=json.dumps({"model": name}).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"name": name, "reachable": False, "error": str(e)}
        details = body.get("details", {})
        return {"name": name, "reachable": True,
                # /api/show does not carry the digest; /api/tags does
                "digest": body.get("digest") or details.get("digest") or self._digest_from_tags(name),
                "parameter_size": details.get("parameter_size"),
                "quantization": details.get("quantization_level"),
                "family": details.get("family"),
                "modified_at": body.get("modified_at")}

    def _openai_identity(self):
        """vLLM and anything else serving /v1/models.

        There is no digest in that API. What identifies the model is the name
        the server was started with, so that is what is recorded, together with
        every model it is serving, which is the closest thing to a manifest.
        """
        name = self.llm_model.split("/", 1)[-1]
        base = self.api_base.rstrip("/")
        url = base + ("/models" if base.endswith("/v1") else "/v1/models")
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"name": name, "reachable": False, "error": str(e), "api": "openai"}
        served = [m.get("id") for m in body.get("data", [])]
        return {"name": name, "reachable": True, "api": "openai",
                "served_models": served,
                "serving_this_model": name in served,
                "digest": None}

    def _digest_from_tags(self, name):
        try:
            with urllib.request.urlopen(f"{self.api_base}/api/tags", timeout=5) as response:
                for model in json.load(response).get("models", []):
                    if model.get("name") == name:
                        return model.get("digest")
        except (urllib.error.URLError, OSError, ValueError):
            return None
        return None

    def describe(self):
        return {"config": asdict(self),
                "llm": self.llm_identity(),
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "code": _git_state(),
                "python": sys.version.split()[0],
                "packages": {p: _version(p) for p in PACKAGES}}

    def require_llm(self, record):
        """Stop unless the record shows the LLM answering under a known identity.

        The case outputs committed on 2026-10-02 record `reachable: false`: the
        server was down and every answer came from DSPy's cache, so nothing in
        them says which model produced them. A run that cannot name its model
        is now refused rather than recorded.
        """
        if self.allow_no_llm:
            return
        llm = record["llm"]
        if not llm.get("reachable"):
            problem = f"not reachable at {self.api_base} ({llm.get('error')})"
        elif llm.get("api") == "openai" and not llm.get("serving_this_model"):
            problem = f"not served there (serving {llm.get('served_models')})"
        elif self.backend == "ollama" and not llm.get("digest"):
            problem = "served, but Ollama reported no digest for it"
        else:
            return
        raise RuntimeError(f"LLM {self.llm_model!r} {problem}. Start the server, or pass "
                           f"--allow-no-llm for a run that is meant to have no answers.")


def _version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _git_state():
    def git(*args):
        try:
            return subprocess.run(("git", *args), capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    # names the release tag when the run is at it (e.g. "revision-final"),
    # and how far past the nearest tag it is otherwise
    described = git("describe", "--tags", "--always", "--dirty")
    return {"commit": commit or None, "describe": described or None,
            "dirty": bool(status) if status is not None else None}


def add_arguments(parser, defaults=RunConfig()):
    """Seed, temperature and LLM options shared by the pipeline and benchmark."""
    parser.add_argument("--seed", type=int, default=defaults.seed)
    parser.add_argument("--temperature", type=float, default=defaults.temperature)
    parser.add_argument("--model", dest="llm_model", default=defaults.llm_model)
    parser.add_argument("--api-base", dest="api_base", default=defaults.api_base,
                        help="the OpenAI-compatible root vLLM serves (…/v1), or "
                             "Ollama's root for an ollama/ model")
    parser.add_argument("--api-key", dest="api_key", default=defaults.api_key,
                        help="sent to an OpenAI-compatible server; vLLM ignores the value")
    parser.add_argument("--model-revision", dest="model_revision", default=defaults.model_revision,
                        help="the Hugging Face revision the server loaded (vllm serve --revision), "
                             "kept in the run record; default: the pinned revision of a known model "
                             "(run_config.MODEL_REVISIONS)")
    parser.add_argument("--few-shot-k", dest="few_shot_k", type=int, default=defaults.few_shot_k)
    parser.add_argument("--prompt", choices=tuple(PROMPTS), default=defaults.prompt,
                        help="the relation classifier's instructions (text2bpmn/prompts.py); "
                             "'published' and 'table3' are the texts behind the published numbers")
    parser.add_argument("--llm-timeout", dest="llm_timeout", type=int, default=defaults.llm_timeout,
                        help="seconds to wait for one relation answer before counting it failed")
    parser.add_argument("--constrained-output", dest="constrained_output",
                        action="store_true", default=defaults.constrained_output,
                        help="decode the answer against a JSON schema whose relation "
                             "field is an enum of the five labels, one call per pair (default)")
    parser.add_argument("--no-constrained-output", dest="constrained_output", action="store_false",
                        help="free-text answers, as the submitted runs (revision-final)")
    parser.add_argument("--reasoning-max-chars", dest="reasoning_max_chars", type=int,
                        default=defaults.reasoning_max_chars,
                        help="with --constrained-output, the longest reasoning the schema allows")
    parser.add_argument("--max-tokens", dest="max_tokens", type=int, default=defaults.max_tokens,
                        help="tokens one reply may generate (default 1024; 0: the server's limit)")
    parser.add_argument("--no-thinking", dest="disable_thinking", action="store_true",
                        default=defaults.disable_thinking,
                        help="ask a hybrid model (Qwen3, Qwen3.5) not to reason before "
                             "answering; vLLM only (default)")
    parser.add_argument("--thinking", dest="disable_thinking", action="store_false",
                        help="leave a hybrid model's reasoning on (its own default)")
    parser.add_argument("--two-phase", dest="two_phase", action="store_true",
                        default=defaults.two_phase,
                        help="on hard pairs only, reason freely then decode the answer "
                             "under constraint (text2bpmn/two_phase.py)")
    parser.add_argument("--llm-cache", dest="llm_cache", action="store_true",
                        default=defaults.llm_cache,
                        help="reuse DSPy's stored answers for unchanged prompts; never for "
                             "a reported run, whose answers must come from the model")
    parser.add_argument("--allow-no-llm", dest="allow_no_llm", action="store_true",
                        default=defaults.allow_no_llm,
                        help="run on although the LLM cannot be reached; only for the "
                             "no-LLM control, where every answer is UNKNOWN by design")
    parser.add_argument("--guardrail-mode", dest="guardrail_mode", default=defaults.guardrail_mode)
    for guard, helptext in (
            ("parallel_mutual", "a block needs PARALLEL in both directions"),
            ("parallel_require_cue", "a block needs a concurrency cue in the text"),
            ("parallel_anchor_guard", "a step that already follows another cannot anchor a block")):
        parser.add_argument(f"--{guard.replace('_', '-')}", dest=guard,
                            action="store_true", default=getattr(defaults, guard),
                            help=helptext)
    parser.add_argument("--parallel-detection", dest="parallel_detection",
                        choices=("cues", "all", "off"), default=defaults.parallel_detection,
                        help="when to ask whether two activities run concurrently")
    parser.add_argument("--relation-mode", dest="relation_mode", choices=("pairs", "decisions", "decisions2", "decisions3", "decisions4",
                                 "pairs2"),
                        default=defaults.relation_mode,
                        help="ask the LLM about pairs (pairs, as submitted; pairs2, idea 2) or once "
                             "per decision (decisions, decisions2, decisions3; decisions4 also once per "
                             "concurrency word: text2bpmn/decisions.py)")
    parser.add_argument("--ontology", dest="ontology_file", default=defaults.ontology_file,
                        help="BPMN ontology to populate")
    parser.add_argument("--ontology-out", dest="ontology_out", default=defaults.ontology_out,
                        help="where to write the populated ontology; omitted, the step is skipped")
    return parser


def from_arguments(args, **overrides):
    fields = {f: getattr(args, f) for f in RunConfig.__dataclass_fields__ if hasattr(args, f)}
    return RunConfig(**{**fields, **overrides}).apply()


def parse_known(argv=None, **overrides):
    """Config from the command line, ignoring any other arguments."""
    args, _ = add_arguments(argparse.ArgumentParser(add_help=False)).parse_known_args(argv)
    return from_arguments(args, **overrides)
