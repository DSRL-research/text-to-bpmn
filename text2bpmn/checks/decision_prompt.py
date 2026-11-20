"""The loan case's decision questions as the release run sent them, rebuilt from the saved run (Section 3.2.4's box).

    python3 -m text2bpmn.checks.decision_prompt [--case loan] [--question 2]
        # -> runs/checks/final-3/open_analyses/decision_prompt_loan.{md,json}

The run does not save prompts: decisions.json keeps each question's node_A
(the decision) and node_B (the items, a decision mention prefixed
"decision: ") and the labels answered. The prompt is a pure function of saved
inputs, so it is rebuilt by replay, as text2bpmn/checks/concurrency_prompt.py
rebuilds the concurrency question: the release code runs again on the spans the
log printed ("Split Entities"), injected as finder3.process_text allows, on the
text the recogniser read (the log's "Coref Resolved" line); each decision
question goes through decisions.ask_llm itself, with a stand-in client that
records the messages and request options and replies with the logged labels.
No LLM is called and no file but the report is written. The replay must ask
the logged questions, in the logged order, and rebuild the saved graph flow
for flow; otherwise the script stops.

The report gives the system message (decisions.INSTRUCTIONS_SAME) whole and
abridged (its worked examples left out, as the paper's box shows it), the user
message of the chosen question verbatim, the request options, and the logged
answer in the schema's form (the run kept no reasoning).
"""
import argparse
import ast
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

from text2bpmn import decisions

RUN = Path("runs/final-3/cases")
OUT = Path("runs/checks/final-3/open_analyses")


def saved(case):
    folder = RUN / case
    log = (folder / "log.txt").read_text(encoding="utf-8")
    extraction = json.loads((folder / "extraction.json").read_text(encoding="utf-8"))
    asked = json.loads((folder / "decisions.json").read_text(encoding="utf-8"))["decisions"]
    context = log.split("(Debug) Coref Resolved: ", 1)[1].split("\n", 1)[0]
    spans = ast.literal_eval(log.split("--- Split Entities ---\n", 1)[1].split("\n", 1)[0])
    return extraction, asked, context, spans


def by_replay(case):
    from text2bpmn import pet_strict as ps
    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    extraction, asked, context, spans = saved(case)
    run = extraction["run_config"]["config"]
    config = RunConfig(relation_mode=run["relation_mode"], allow_no_llm=True, api_base="http://127.0.0.1:1",
                       llm_timeout=5, ontology_out="")
    with contextlib.redirect_stdout(io.StringIO()):
        x = BPMNHybridExtractor(config=config, ner_model_path=None)
    logged = {(q["node_A"], q["node_B"]): q["label"].split() for q in asked if q.get("source") == "llm"}
    sent = []
    cfg = SimpleNamespace(constrained_output=run["constrained_output"], reasoning_max_chars=run["reasoning_max_chars"])

    def ask_decision(ctx, decision, steps, lanes, kinds=None):
        pair = (x._relation_text(decision),
                " | ".join(("decision: " if k == "decision" else "") + x._relation_text(s)
                           for s, k in zip(steps, kinds or ["step"] * len(steps))))
        labels = logged[pair]

        def client(messages, **options):  # stands in for dspy.settings.lm
            sent.append({"node_A": pair[0], "node_B": pair[1], "messages": messages, "options": options,
                         "lanes": list(lanes), "labels": labels})
            return [json.dumps({"reasoning": "", **{f"step_{k}": v for k, v in enumerate(labels, 1)}})]

        return decisions.ask_llm(client, ctx, decision, steps, x._relation_text, lanes, cfg, kinds)

    def ask_parallel(ctx, cue, steps, lanes):
        return logged.get(("parallel: " + x._relation_text(cue), " | ".join(x._relation_text(s) for s in steps)))

    x._ask_decision, x._ask_parallel = ask_decision, ask_parallel
    injected = [{"start": s["start"], "end": s["end"], "label": s["entity_group"], "score": s["score"]}
                for s in spans]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = x.process_text(context, entities={"text": context, "spans": injected, "source": "replay"})
    return {"sent": sent, "same_graph": ps._span_flows(result) == ps._span_flows(extraction),
            "asked_as_logged": [(q["node_A"], q["node_B"]) for q in sent]
            == [(q["node_A"], q["node_B"]) for q in asked if q.get("source") == "llm"],
            "config": run}


def abridged(instructions):
    """The instructions without their worked examples, as the paper's box shows them."""
    head, examples = instructions.split("\n\nExample.", 1)[0], instructions.count("\n\nExample.")
    tail = instructions.rsplit("\n\n", 1)[1]
    words = {1: "one", 2: "two", 3: "three", 4: "four"}.get(examples, str(examples))
    return f"{head}\n\n[... {words} worked examples ...]\n\n{tail}", examples


def analyse(case="loan", number=2):
    replay = by_replay(case)
    assert replay["same_graph"], "the replay does not rebuild the saved graph"
    assert replay["asked_as_logged"], "the replay does not ask the logged questions in the logged order"
    chosen = replay["sent"][number - 1]
    system, user = chosen["messages"][0]["content"], chosen["messages"][1]["content"]
    short, examples = abridged(system)
    c = replay["config"]
    return {"case": str(RUN / case), "questions": len(replay["sent"]), "question": number,
            "logged": {"node_A": chosen["node_A"], "node_B": chosen["node_B"], "label": " ".join(chosen["labels"])},
            "system_message": system, "system_message_abridged": short, "worked_examples": examples,
            "system_is_INSTRUCTIONS_SAME": system == decisions.INSTRUCTIONS_SAME,
            "user_message": user, "lanes_of_the_items": chosen["lanes"], "request_options": chosen["options"],
            "answer": {f"step_{k}": v for k, v in enumerate(chosen["labels"], 1)},
            "request_settings": {"model": c["llm_model"], "temperature": c["temperature"], "seed": c["seed"],
                                 "max_tokens": c["max_tokens"],
                                 "extra_body": {"chat_template_kwargs": {"enable_thinking": not c["disable_thinking"]}}},
            "other_questions": [{"node_A": q["node_A"], "node_B": q["node_B"], "label": " ".join(q["labels"])}
                                for k, q in enumerate(replay["sent"], 1) if k != number],
            "replay": {"same_graph_as_saved": True, "asked_as_logged": True},
            "code": {"messages": "text2bpmn/decisions.py ask_llm (system INSTRUCTIONS_SAME when the items have "
                                 "kinds, user question)"}}


def markdown(r):
    fence = "```"
    return "\n".join([
        f"# Decision question {r['question']} of {r['questions']} of `{r['case']}`, as the release run sent it", "",
        "Generated by `text2bpmn/checks/decision_prompt.py` from the run's log.txt, extraction.json and "
        "decisions.json, by a replay that asks the logged questions in the logged order and rebuilds the saved "
        "graph.", "",
        f"Logged: node_A `{r['logged']['node_A']}`, node_B `{r['logged']['node_B']}`, answer `{r['logged']['label']}`.",
        "", f"## System message, abridged ({r['worked_examples']} worked examples left out)", "", fence + "text",
        r["system_message_abridged"], fence, "",
        "## User message (verbatim, `decisions.question`)", "", fence + "text", r["user_message"], fence, "",
        "## Answer (the logged labels in the schema's form; the run kept no reasoning)", "", fence + "json",
        json.dumps(r["answer"], ensure_ascii=False), fence, "",
        "## Request options", "", fence + "json",
        json.dumps({**r["request_options"], **r["request_settings"]}, indent=1, ensure_ascii=False), fence, "",
        "## The other questions of the case", ""]
        + [f"- node_A `{q['node_A']}`, node_B `{q['node_B']}`: `{q['label']}`" for q in r["other_questions"]]
        + ["", "## System message, whole", "", fence + "text", r["system_message"], fence, ""])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", default="loan")
    ap.add_argument("--question", type=int, default=2, help="which of the case's decision questions, from 1")
    args = ap.parse_args()
    result = analyse(args.case, args.question)
    out = OUT / f"decision_prompt_{args.case}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    text = markdown(result)
    out.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
