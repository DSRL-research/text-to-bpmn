"""Pilot run with a scripted LM: the same documents as pilot_run, with the
relation answers given by keyword rules instead of a model, so that decisions
and parallel blocks reach the structural checks without a GPU.

    python3 -m text2bpmn.checks.scripted_pilot [--out runs/pilot_scripted]

PILOT ONLY. Its answers say nothing about the method. It is kept out of every
real run three ways: it is its own entry point, which nothing else imports; it
refuses an output folder that is not a pilot folder; and every run record it
writes carries "scripted_llm": true, beside an LLM identity that names the
script rather than a model.

The rules, for the pair finder3 asks about (node_A, node_B):

    node_A opens with "otherwise" or "else", node_B its first candidate   FALSE_BRANCH
    node_A opens with "if", node_B its first candidate                    TRUE_BRANCH
    node_B's sentence has "meanwhile", "simultaneously", "in parallel"
      or "at the same time"                                               PARALLEL
    anything else                                                         SEQUENCE

Which candidate a pair is, and node_B's sentence, are not in the prompt, so
the harness wraps this extractor's _predict_relation -- on the one instance,
not in finder3 -- to hand both to the LM before each call. The answer still
goes through DSPy and the pipeline's own parsing.

The run-hygiene check that a real run passes (a reachable server and a model
digest, RunConfig.require_llm) is bypassed here with allow_no_llm, the switch
that exists for runs meant to have no model; nothing in the pipeline changes.
"""
import argparse
import re
import time
from pathlib import Path

import dspy

from text2bpmn.checks.pilot_run import documents, run_one, summarise

FIELD = re.compile(r"\[\[ ## (\w+) ## \]\]\n(.*?)(?=\n\n\[\[ ## |\Z)", re.S)
ELSE = re.compile(r"^\s*(?:otherwise|else)\b", re.I)
IF = re.compile(r"^\s*if\b", re.I)
CONCURRENT = re.compile(r"\b(?:meanwhile|simultaneously|in parallel|at the same time)\b", re.I)
SENTENCE_END = re.compile(r"[.!?;]")


def scripted_relation(node_a, node_b_sentence, first):
    if ELSE.search(node_a) and first:
        return "FALSE_BRANCH", "node_A is an else-marker, node_B its first candidate"
    if IF.search(node_a) and first:
        return "TRUE_BRANCH", "node_A opens a condition, node_B its first candidate"
    if CONCURRENT.search(node_b_sentence):
        return "PARALLEL", "a concurrency cue in node_B's sentence"
    return "SEQUENCE", "no rule applies"


def sentence_at(text, offset):
    """The sentence of `text` around character `offset`."""
    if offset is None:
        return ""
    starts = [m.end() for m in SENTENCE_END.finditer(text, 0, offset)]
    start = starts[-1] if starts else 0
    end = SENTENCE_END.search(text, offset)
    return text[start:end.end() if end else len(text)]


class ScriptedLM(dspy.LM):
    """Answers in the ChatAdapter's own format, as dspy.utils.DummyLM does."""

    def __init__(self):
        super().__init__("scripted", "chat", 0.0, 1000, False)
        self.answered = 0
        self.first = False
        self.node_b_sentence = ""

    def __call__(self, prompt=None, messages=None, **kwargs):
        fields = dict(FIELD.findall(messages[-1]["content"]))
        label, why = scripted_relation(fields.get("node_A", ""),
                                       self.node_b_sentence or fields.get("node_B", ""), self.first)
        self.answered += 1
        return [f"[[ ## reasoning ## ]]\nscripted: {why}\n\n"
                f"[[ ## relation ## ]]\n{label}\n\n[[ ## completed ## ]]"]


def instrument(extractor, lm):
    """Tell the LM, before each relation call, whether node_B is the first
    candidate asked about for this node_A, and node_B's sentence."""
    original = extractor._predict_relation
    state = {"head": None}

    def predict(context, current, candidate):
        lm.first = state["head"] != current.get("id")
        state["head"] = current.get("id")
        lm.node_b_sentence = sentence_at(context, candidate.get("start"))
        return original(context, current, candidate)

    extractor._predict_relation = predict


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="runs/pilot_scripted")
    ap.add_argument("--only", nargs="*", help="run only these document ids")
    args = ap.parse_args()
    out = Path(args.out)
    if not any(part.startswith("pilot") for part in out.parts) or "final" in out.parts:
        raise SystemExit(f"refusing {out}: the scripted LM writes only to a pilot folder")

    from text2bpmn.finder3 import NER_MODEL_PATH, BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    out.mkdir(parents=True, exist_ok=True)
    docs = [d for d in documents() if not args.only or d[0] in args.only]
    begin = time.perf_counter()
    config = RunConfig(allow_no_llm=True, llm_cache=False, prompt="corrected")
    extractor = BPMNHybridExtractor(config=config, ner_model_path=NER_MODEL_PATH)
    lm = ScriptedLM()
    dspy.settings.configure(lm=lm)  # replaces the LM finder3 configured; the predictor reads it per call
    instrument(extractor, lm)
    extractor.run_record = {**extractor.run_record, "scripted_llm": True,
                            "llm": {"name": "scripted (text2bpmn/checks/scripted_pilot.py)",
                                    "reachable": None, "digest": None, "scripted_llm": True}}
    load_seconds = round(time.perf_counter() - begin, 2)

    records = []
    for index, (doc_id, text) in enumerate(docs, 1):
        record = run_one(extractor, doc_id, text, out / doc_id)
        records.append(record)
        print(f"[{index}/{len(docs)}] {doc_id}: {record['status']} in {record['seconds']} s"
              + (f" -- {record['error']}" if record.get("error") else ""), flush=True)
    summary = summarise(records, extractor.run_record, load_seconds,
                        round(time.perf_counter() - begin, 2), out,
                        title="Pilot run, scripted LM (keyword rules, not a model)")
    print(f"{summary['finished']}/{summary['documents']} finished; {lm.answered} scripted answers; "
          f"summary in {out / 'summary.md'}")


if __name__ == "__main__":
    main()
