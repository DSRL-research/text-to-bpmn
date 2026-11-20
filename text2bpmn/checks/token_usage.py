"""Tokens per LLM call in the release run: prompts counted exactly, answers from vLLM's log.

    python3 -m text2bpmn.checks.token_usage     # -> text2bpmn/results/token_usage.{md,json}

The runs record no token counts, and the replies' reasoning is not kept, only
their labels. Two sources give them instead:

- **Prompt tokens, exactly.** The release run's PET questions are rebuilt by
  replaying the run (each question answered with the answer it logged, so the
  same questions are asked in the same order) and counted with Qwen3.5's own
  tokenizer at the served revision, under the chat template with thinking off,
  as the server received them. (The case and lane experiments read the
  recogniser's spans, not PET's gold ones, so they are not replayed here.)
- **Answer tokens, from the server's log.** vLLM logs its average prompt and
  generation throughput every few seconds; throughput times the interval since
  the previous line is the tokens processed in it. Summed over each
  experiment's time window (from its run record) and divided by its calls,
  that is tokens per call. The estimate is checked where the exact count is
  known: the PET window's prompt tokens must equal the rebuilt prompts'.

The log is `runs/final-3/vllm.log`: the server process that answered every run
from 2026-11-09 to 2026-11-12, in UTC.
"""
import contextlib
import io
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

MODEL, REVISION = "Qwen/Qwen3.5-27B-FP8", "97f5941bf617e31c5e237364a8602ce3f03a551a"
LOG = Path("runs/final-3/vllm.log")
OUT = Path("text2bpmn/results/token_usage")
# the release run's experiments that asked the LLM: (summary, experiment)
EXPERIMENTS = [("runs/final-3", "pet_decisions"), ("runs/final-3", "cases"), ("runs/final-3", "coref_ablation"),
               ("runs/gliner-3", "cases_gliner"), ("runs/gliner-3", "lanes_gliner")]
STAT = re.compile(r"INFO (\d\d-\d\d) (\d\d:\d\d:\d\d) \[loggers\.py:\d+\] Engine 000: Avg prompt throughput: "
                  r"([\d.]+) tokens/s, Avg generation throughput: ([\d.]+) tokens/s")


def log_intervals(lines, year=2026):
    """[(time, prompt tokens, generated tokens, requests)] per throughput line, each
    over the interval since the line before it (10 s for the first)."""
    out, previous, requests = [], None, 0
    for line in lines:
        if "POST /v1/chat/completions" in line:
            requests += 1
            continue
        m = STAT.search(line)
        if not m:
            continue
        t = datetime.strptime(f"{year}-{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
        seconds = (t - previous).total_seconds() if previous else 10.0
        out.append((t, float(m.group(3)) * seconds, float(m.group(4)) * seconds, requests))
        previous, requests = t, 0
    return out


def in_window(intervals, start, end, slack=12):
    """Prompt tokens, generated tokens and requests logged after start, up to
    `slack` seconds after end (the line that reports the last interval)."""
    rows = [r for r in intervals if start < r[0] <= end + timedelta(seconds=slack)]
    return sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows)


def windows():
    """{experiment: (start, end, LLM calls)} from the runs' summaries and run records."""
    out = {}
    for root, name in EXPERIMENTS:
        summary = json.loads(Path(root, "summary.json").read_text(encoding="utf-8"))
        record = json.loads(Path(root, name, "run_record.json").read_text(encoding="utf-8"))
        end = datetime.fromisoformat(record["finished"]).replace(tzinfo=None)
        start = end - timedelta(seconds=summary["experiments"][name]["seconds"])
        calls = sum(json.loads(p.read_text(encoding="utf-8")).get("document", {}).get("relation_calls", 0)
                    for p in Path(root, name).rglob("run_record.json") if p.parent != Path(root, name))
        if name.startswith("pet_"):
            calls = json.loads(Path(root, name, "result.json").read_text(encoding="utf-8"))["relation_calls"]
        out[name] = (start, end, calls)
    return out


def prompt_tokens():
    """{question kind: [prompt tokens]} of the release run's PET questions."""
    from transformers import AutoTokenizer

    from text2bpmn import decisions
    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    count = lambda system, user: len(tokenizer.apply_chat_template(  # noqa: E731
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        add_generation_prompt=True, enable_thinking=False))
    config = RunConfig(relation_mode="decisions4", allow_no_llm=True, api_base="http://127.0.0.1:1",
                       llm_timeout=5, ontology_out="")
    with contextlib.redirect_stdout(io.StringIO()):
        x = BPMNHybridExtractor(config=config, ner_model_path=None)
    sizes = defaultdict(list)
    for job in json.loads(Path("text2bpmn/baselines/pet_jobs.json").read_text(encoding="utf-8"))["jobs"]:
        saved = json.loads(Path("runs/final-3/pet_decisions/documents", job["name"], "process.json")
                           .read_text(encoding="utf-8"))
        logged = defaultdict(list)
        for r in saved["relation_parsing"]["decisions"]:
            if r.get("source") == "llm":
                logged[(r["node_A"], r["node_B"])].append(r["label"])

        def ask_decision(context, d, steps, lanes, kinds=None):
            pair = (x._relation_text(d), " | ".join(("decision: " if k == "decision" else "") + x._relation_text(s)
                                                    for s, k in zip(steps, kinds or ["step"] * len(steps))))
            sizes["decision"].append(count(decisions.INSTRUCTIONS_SAME,
                                           decisions.question(context, d, steps, x._relation_text, lanes, kinds)))
            answers = logged.get(pair)
            return answers.pop(0).split() if answers else None

        def ask_parallel(context, cue, steps, lanes):
            pair = ("parallel: " + x._relation_text(cue), " | ".join(x._relation_text(s) for s in steps))
            sizes["concurrency"].append(count(decisions.INSTRUCTIONS_PARALLEL,
                                              decisions.parallel_question(context, cue, steps, x._relation_text,
                                                                          lanes)))
            answers = logged.get(pair)
            return answers.pop(0).split() if answers else None

        x._ask_decision, x._ask_parallel = ask_decision, ask_parallel
        spans = [{"start": s["start"], "end": s["end"], "label": s["label"], "score": 1.0} for s in job["spans"]]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            x.process_text(job["text"], entities={"text": job["text"], "spans": spans, "source": "replay"})
    return dict(sizes)


def main():
    exact = prompt_tokens()
    intervals = log_intervals(LOG.read_text(encoding="utf-8", errors="replace").splitlines())
    rows, total = {}, [0.0, 0.0, 0, 0]
    for name, (start, end, calls) in windows().items():
        prompt, generated, requests = in_window(intervals, start, end)
        rows[name] = {"calls": calls, "requests_logged": requests, "prompt_tokens": round(prompt),
                      "generated_tokens": round(generated), "prompt_per_call": prompt / calls,
                      "generated_per_call": generated / calls, "window": [start.isoformat(), end.isoformat()]}
        total = [total[0] + prompt, total[1] + generated, total[2] + requests, total[3] + calls]
    pet_exact = sum(sum(v) for v in exact.values())
    result = {"model": MODEL, "revision": REVISION,
              "exact_prompt_tokens": {k: {"questions": len(v), "mean": statistics.mean(v),
                                          "median": statistics.median(v), "max": max(v), "total": sum(v)}
                                      for k, v in exact.items()},
              "from_the_log": rows,
              "total": {"calls": total[3], "prompt_tokens": round(total[0]), "generated_tokens": round(total[1]),
                        "prompt_per_call": total[0] / total[3], "generated_per_call": total[1] / total[3]},
              "check": {"pet_prompt_tokens_exact": pet_exact,
                        "pet_prompt_tokens_from_log": rows["pet_decisions"]["prompt_tokens"]}}
    if result["check"]["pet_prompt_tokens_exact"] != result["check"]["pet_prompt_tokens_from_log"]:
        # The exact count must equal the server's own count of the same window; if it does not, the
        # tokenizer counted something else (transformers 5, for one, returns a BatchEncoding whose len()
        # is its number of keys). Nothing is written, so the committed result is not overwritten.
        raise SystemExit(f"token_usage: the PET window's prompt tokens from the log "
                         f"({result['check']['pet_prompt_tokens_from_log']:,}) differ from the exact count "
                         f"({pet_exact:,}); nothing written. Is transformers the pinned 4.50.0 (requirements.txt)?")
    lines = ["# Tokens per LLM call in the release run (revision-final-3)", "",
             "Generated by `text2bpmn/checks/token_usage.py`; see its docstring for the method.", "",
             f"**Exact prompt tokens** of the PET questions, rebuilt by replay and counted with {MODEL}'s tokenizer "
             f"at revision `{REVISION[:12]}`, chat template, thinking off:", "",
             "| question | questions | mean | median | max | total |", "|---|---|---|---|---|---|"]
    lines += [f"| {k} | {v['questions']} | {v['mean']:.0f} | {v['median']:.0f} | {v['max']} | {v['total']:,} |"
              for k, v in result["exact_prompt_tokens"].items()]
    c = result["check"]
    lines += ["", f"**From the server's log**, each experiment's window (`{LOG}`). Check: the PET window's prompt "
              f"tokens from the log, {c['pet_prompt_tokens_from_log']:,}, against the exact count, "
              f"{c['pet_prompt_tokens_exact']:,}.", "",
              "| experiment | calls | requests logged | prompt tokens | per call | answer tokens | per call |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {k} | {v['calls']} | {v['requests_logged']} | {v['prompt_tokens']:,} | {v['prompt_per_call']:,.0f} | "
              f"{v['generated_tokens']:,} | {v['generated_per_call']:,.0f} |" for k, v in rows.items()]
    t = result["total"]
    lines.append(f"| **all** | {t['calls']} | | {t['prompt_tokens']:,} | {t['prompt_per_call']:,.0f} | "
                 f"{t['generated_tokens']:,} | {t['generated_per_call']:,.0f} |")
    OUT.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
