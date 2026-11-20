"""Measure the FALSE_BRANCH guardrail's effect exactly by replaying it on a
stored benchmark run (ticket C2).

    python3 -m text2bpmn.guardrail_replay --dataset benchmark_silver_2.jsonl \
        --report benchmark_results_silver_fewshot_final2.md [--model dspy|bert]

The stored predictions already passed through the legacy guardrail (mode
"entity_2"). Where that guardrail fired, the model's raw prediction is not
recoverable, so the replay refuses to run unless it provably never fired.
Otherwise the stored predictions are the raw model outputs, and each mode's
effect is measured on identical inputs, with no LLM re-run and no sampling
noise.

The rule can only fire where an explicit marker is present, so the effect is
also reported on three partitions of the benchmark: every sample, those
carrying a marker, and those carrying none. The last is the honest bound on
what the rule contributes, because on it every mode is identical by
construction and FALSE_BRANCH recall is the model's own.
"""
import argparse
from pathlib import Path

from text2bpmn.guardrails import MODES, false_branch_guardrail, has_marker
from text2bpmn.relation_metrics import LABELS, MODEL_COLUMN, compute, load_dataset, predictions_from_report


PARTITIONS = ("all", "with_marker", "marker_free")


def partition(samples, which):
    """Indices of the samples in one partition (see PARTITIONS)."""
    if which not in PARTITIONS:
        raise ValueError(f"unknown partition {which!r}; expected one of {PARTITIONS}")
    marked = {i for i, s in enumerate(samples)
              if has_marker(s["entity_1"]) or has_marker(s["entity_2"])}
    if which == "all":
        return list(range(len(samples)))
    if which == "with_marker":
        return sorted(marked)
    return [i for i in range(len(samples)) if i not in marked]


def replay_partitions(samples, stored):
    """Every mode's effect on each partition, with that partition's size and
    how many of its samples are really FALSE_BRANCH."""
    out = {}
    for which in PARTITIONS:
        index = partition(samples, which)
        part = [samples[i] for i in index]
        out[which] = {
            "n": len(index),
            "false_branch_support": sum(s["label"] == "FALSE_BRANCH" for s in part),
            "modes": replay(part, [stored[i] for i in index]),
        }
    return out


def to_markdown(results, model):
    lines = [f"Guardrail replay for the stored `{model}` predictions, by whether the",
             "pair carries an explicit else-marker. A mode can only differ from `off`",
             "where a marker is present, so the `marker_free` rows are the model's own",
             "performance and bound what the rule can contribute.", ""]
    for which, block in results.items():
        lines += [f"## {which} ({block['n']} samples, {block['false_branch_support']} really FALSE_BRANCH)",
                  "",
                  "| Mode | Fired | Accuracy | " + " | ".join(f"{c} P / R" for c in LABELS) + " |",
                  "| --- " * (len(LABELS) + 3) + "|"]
        for mode, r in block["modes"].items():
            m = r["metrics"]
            cells = " | ".join(f"{m['per_class'][c]['precision']:.3f} / {m['per_class'][c]['recall']:.3f}"
                               for c in LABELS)
            lines.append(f"| {mode} | {r['fired']} | {m['correct']}/{m['n']} ({m['accuracy']:.3f}) | {cells} |")
        lines.append("")
    return "\n".join(lines)


def replay(samples, stored):
    fired = [s for s, p in zip(samples, stored) if p == "FALSE_BRANCH" and has_marker(s["entity_2"])]
    if fired:
        raise ValueError(f"legacy guardrail may have fired on {len(fired)} samples; raw predictions unknown")
    truth = [s["label"] for s in samples]
    results = {}
    for mode in MODES:
        preds = [false_branch_guardrail(p, s["entity_1"], s["entity_2"], mode) for s, p in zip(samples, stored)]
        results[mode] = {"metrics": compute(truth, preds),
                         "fired": sum(a != b for a, b in zip(preds, stored))}
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--model", choices=sorted(MODEL_COLUMN), default="dspy")
    ap.add_argument("--out", help="write the report here as well as printing it")
    args = ap.parse_args()
    samples = load_dataset(args.dataset)
    stored = predictions_from_report(args.report, samples, args.model)
    text = to_markdown(replay_partitions(samples, stored), args.model)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"\n✅ Wrote {args.out}")


if __name__ == "__main__":
    main()
