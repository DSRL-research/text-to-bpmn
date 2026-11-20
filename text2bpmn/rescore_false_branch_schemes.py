"""Rescore the 302-pair relation benchmarks under both FALSE_BRANCH labelling schemes.

    python3 -m text2bpmn.rescore_false_branch_schemes [--runs runs/final]

benchmark_silver_2.jsonl labels FALSE_BRANCH 69 pairs. 46 carry an explicit
else-marker in a node ("otherwise", "else", "if not": guardrails.has_marker).
The other 23 all have one shape: "If X, do A. If Y, do B", the pair being
Y -> B ("If the visa is approved, stamp the passport. If rejected, issue a
formal notice": "If rejected" -> "issue a formal notice"). In 22 of them Y is
the complement of X; in one (line 210, a folder created / deleted) it is only
a second condition. The dataset reads B as the false branch of the first
condition; the syntactic scheme -- the branch taken when the stated condition
holds is TRUE_BRANCH -- reads it as the true branch of its own condition Y.
None of the 73 TRUE_BRANCH pairs is labelled against that scheme. This scores
each run both ways:

- dataset: the labels as they are;
- syntactic: the 23 marker-free FALSE_BRANCH pairs relabelled TRUE_BRANCH.

The answers are read from each run's log.txt, one "[LLM Debug] Relation:" line
per pair, in the order benchmark_relations.py asked them: random.sample of the
dataset with the run's seed. The order is checked by recomputing the report's
own accuracy from the log, and the script stops if they differ.

Writes text2bpmn/results/false_branch_schemes.md and .json.
"""
import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from text2bpmn.guardrails import has_marker

DATASET = "benchmark_silver_2.jsonl"
BENCHMARKS = ("table3_302", "corrected_302")


def load(path=DATASET):
    """The dataset as benchmark_relations.py reads it."""
    data = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        line = line[:-1] if line.endswith(",") else line
        line = line[:-1] if line.endswith(".") else line
        try:
            data.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return data


def answers(run_dir, data):
    """{dataset index: answer} for one benchmark run."""
    record = json.loads((run_dir / "benchmark_run.json").read_text(encoding="utf-8"))
    log = (run_dir / "log.txt").read_text(encoding="utf-8")
    given = re.findall(r"^\[LLM Debug\] Relation: (\S+)", log, re.M)
    random.seed(record["config"]["seed"])
    order = random.sample(range(len(data)), len(given))
    report = (run_dir / "benchmark.md").read_text(encoding="utf-8")
    reported = int(re.search(r"\*\*DSPy \([^)]*\)\*\* \| \*\*[\d.]+%\*\* \| (\d+)/", report).group(1))
    recomputed = sum(a == data[i]["label"] for i, a in zip(order, given))
    if recomputed != reported:
        raise SystemExit(f"{run_dir}: {recomputed} correct from the log, {reported} in the report; "
                         "the order is not the one the benchmark used")
    return dict(zip(order, given))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", default="runs/final")
    ap.add_argument("--out", default="text2bpmn/results/false_branch_schemes")
    args = ap.parse_args(argv)
    data = load()
    relabelled = sorted(i for i, d in enumerate(data) if d["label"] == "FALSE_BRANCH"
                        and not (has_marker(d["entity_1"]) or has_marker(d["entity_2"])))
    syntactic = [("TRUE_BRANCH" if i in relabelled else d["label"]) for i, d in enumerate(data)]
    results = {"dataset": DATASET, "pairs": len(data), "relabelled": relabelled, "runs": {}}
    lines = ["# The 302-pair benchmarks under both FALSE_BRANCH labelling schemes", "",
             f"Runs in `{args.runs}`, rescored by `text2bpmn/rescore_false_branch_schemes.py`. "
             f"**dataset**: the labels of `{DATASET}`. **syntactic**: the {len(relabelled)} FALSE_BRANCH "
             "pairs without an else-marker relabelled TRUE_BRANCH, the branch taken when the stated "
             "condition holds. No model is run again.", "",
             "| run | dataset labels | syntactic scheme | errors (dataset) | errors (syntactic) | "
             f"answers on the {len(relabelled)} relabelled pairs |", "|---|---|---|---|---|---|"]
    for name in BENCHMARKS:
        run_dir = Path(args.runs) / name
        given = answers(run_dir, data)
        idx = sorted(given)
        dataset_ok = sum(given[i] == data[i]["label"] for i in idx)
        syntactic_ok = sum(given[i] == syntactic[i] for i in idx)
        err_d = Counter(f"{data[i]['label']}->{given[i]}" for i in idx if given[i] != data[i]["label"])
        err_s = Counter(f"{syntactic[i]}->{given[i]}" for i in idx if given[i] != syntactic[i])
        on_relabelled = Counter(given[i] for i in relabelled if i in given)
        results["runs"][name] = {"pairs": len(idx), "dataset_correct": dataset_ok,
                                 "syntactic_correct": syntactic_ok, "errors_dataset": dict(err_d),
                                 "errors_syntactic": dict(err_s),
                                 "answers_on_relabelled": dict(on_relabelled),
                                 "answers": {str(i): given[i] for i in idx}}
        fmt = lambda c: ", ".join(f"{k} {v}" for k, v in c.most_common())
        lines.append(f"| {name} | {dataset_ok}/{len(idx)} ({100 * dataset_ok / len(idx):.1f}%) | "
                     f"{syntactic_ok}/{len(idx)} ({100 * syntactic_ok / len(idx):.1f}%) | {fmt(err_d)} | "
                     f"{fmt(err_s)} | {fmt(on_relabelled)} |")
    lines += ["", f"Relabelled pairs (line index in `{DATASET}`, from 0): "
              + ", ".join(map(str, relabelled)) + "."]
    Path(args.out + ".json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    Path(args.out + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
