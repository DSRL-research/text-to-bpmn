"""The entity-recognition comparison table, from saved spans.

    python3 -m text2bpmn.ner_comparison --spec text2bpmn/baselines/comparison_spec.json \
        --data pet_test.json --out text2bpmn/results/ner_comparison.md

Every model is scored by text2bpmn/eval_ner.py over one label scope, from spans
saved by its own single pass over the data, so no model is run here and the
held-out set is never touched again. A model that cannot emit a label in the
scope is reported as such and given a second pair of averages over the labels
it can emit, rather than being averaged against zeros it had no way to avoid.

The spec is a list of entries, each naming the saved spans and, where the model
has one, the score threshold chosen on the development split:

    [{"name": "...", "spans": "...json", "score_threshold": 0.3, "note": "..."}]

What a model can emit is read from its own run record: the label set for a
fine-tuned checkpoint, the prompted classes for a zero-shot one.
"""
import argparse
import json
from pathlib import Path

from text2bpmn.eval_ner import (BOOTSTRAP_RESAMPLES, assemble, load_pet, load_predictions)

# the fixed label list: the six classes PET annotates in this split, plus the
# one the corpus barely annotates at all, which the paper reports rather than
# hides. AND Gateway has no gold span in the held-out split, so it can only ever
# cost a model false positives; the macro is therefore given twice, over the
# whole list and over the classes that have support.
PET_SCOPE = ["Activity", "Activity Data", "Actor", "AND Gateway",
             "Condition Specification", "Further Specification", "XOR Gateway"]


def emittable_labels(run):
    """The labels this model could produce at all."""
    if run.get("labels_the_model_can_emit"):
        return sorted(run["labels_the_model_can_emit"])
    if run.get("prompts"):
        return sorted(run["prompts"])
    return None


def score_all(spec, data, scope=PET_SCOPE, bootstrap=BOOTSTRAP_RESAMPLES, seed=0):
    sentences = len(load_pet(data))
    results = []
    for entry in spec:
        saved = json.loads(Path(entry["spans"]).read_text(encoding="utf-8"))
        run = saved.get("run", {})
        predicted = load_predictions(entry["spans"], sentences, entry.get("score_threshold"))
        emittable = emittable_labels(run)
        result = assemble(data, predicted, scope=scope, emittable=emittable,
                          bootstrap=bootstrap, seed=seed, model_name=entry["name"])
        # A model may predict a class the scheme does not contain: checkpoint-168
        # emits TASK_INFO, which PET has no label for. Those spans are wrong
        # wherever they land, so the scope is also widened to count them, and
        # both readings are reported rather than the flattering one alone.
        outside = sorted(result["strict"]["predictions_outside_the_scope"])
        if outside:
            result["with_out_of_scheme_counted"] = assemble(
                data, predicted, scope=list(scope) + outside, emittable=emittable,
                bootstrap=bootstrap, seed=seed, model_name=entry["name"])
        result["entry"] = {**entry, "run": run}
        results.append(result)
    return results


def macro_over_supported(result, criterion, support):
    """Macro F1 over the classes the split actually contains."""
    labels = [label for label in result["label_scope"] if support.get(label)]
    if not labels:
        return 0.0
    return round(sum(result[criterion]["per_label"][label]["f1"] for label in labels)
                 / len(labels), 3)


def to_markdown(results, data, scope=PET_SCOPE):
    gold = results[0]
    support = {label: gold["strict"]["per_label"][label]["support"] for label in scope}
    lines = [f"# Entity recognition on {Path(data).name}", "",
             f"{gold['sentences']} sentences, {gold['gold_spans']} gold spans. "
             f"Label scope: {', '.join(scope)}.", "",
             "Support per class: " + ", ".join(f"{l} {support[l]}" for l in scope) + ".",
             "",
             "Micro F1 with a 95% bootstrap interval over the sentences "
             f"({gold['strict'].get('bootstrap_micro_f1', {}).get('resamples', 0)} resamples). "
             "A class a model cannot emit is excluded from the bracketed averages.", "",
             "| Model | strict micro F1 [95% CI] | relaxed micro F1 [95% CI] | strict macro F1 "
             "(supported classes) | cannot emit | spans | out-of-scheme spans |",
             "|---|---|---|---|---|---|---|"]
    for result in results:
        strict, relaxed = result["strict"], result["relaxed"]
        sci, rci = strict.get("bootstrap_micro_f1", {}), relaxed.get("bootstrap_micro_f1", {})
        cannot = ", ".join(result["cannot_emit"]) or "-"
        outside = strict["predictions_outside_the_scope"]
        outside_text = ", ".join(f"{label} {count}" for label, count in outside.items()) or "-"
        lines.append(
            f"| {result['model']} | {strict['micro']['f1']} "
            f"[{sci.get('ci95_low')}, {sci.get('ci95_high')}] | "
            f"{relaxed['micro']['f1']} [{rci.get('ci95_low')}, {rci.get('ci95_high')}] | "
            f"{macro_over_supported(result, 'strict', support)} | {cannot} | "
            f"{result['predicted_spans']} | {outside_text} |")

    widened = [r for r in results if r.get("with_out_of_scheme_counted")]
    if widened:
        lines += ["", "The table above does not count a span whose predicted class is outside the "
                      "scheme, which is generous to a model that emits one. Counting those as "
                      "errors instead:", "",
                  "| Model | strict micro F1 [95% CI] | relaxed micro F1 |", "|---|---|---|"]
        for result in widened:
            block = result["with_out_of_scheme_counted"]
            ci = block["strict"].get("bootstrap_micro_f1", {})
            lines.append(f"| {result['model']} | {block['strict']['micro']['f1']} "
                         f"[{ci.get('ci95_low')}, {ci.get('ci95_high')}] | "
                         f"{block['relaxed']['micro']['f1']} |")

    restricted = [r for r in results if r["cannot_emit"]]
    if restricted:
        lines += ["", "Over the labels each model can emit:", "",
                  "| Model | labels | strict micro F1 [95% CI] | relaxed micro F1 |",
                  "|---|---|---|---|"]
        for result in restricted:
            emittable = [l for l in result["label_scope"] if l not in result["cannot_emit"]]
            strict = result["strict"]
            ci = strict.get("bootstrap_micro_f1_over_emittable_labels", {})
            lines.append(
                f"| {result['model']} | {', '.join(emittable)} | "
                f"{strict['micro_over_emittable_labels']['f1']} "
                f"[{ci.get('ci95_low')}, {ci.get('ci95_high')}] | "
                f"{result['relaxed']['micro_over_emittable_labels']['f1']} |")

    for criterion in ("strict", "relaxed"):
        lines += ["", f"## Per class, {criterion}", "",
                  "| Class | Support | " + " | ".join(r["model"] for r in results) + " |",
                  "|---" * (len(results) + 2) + "|"]
        for label in scope:
            cells = []
            for result in results:
                scores = result[criterion]["per_label"][label]
                cells.append("cannot emit" if label in result["cannot_emit"]
                             else f"{scores['f1']} ({scores['precision']}/{scores['recall']})")
            lines.append(f"| {label} | {support[label]} | " + " | ".join(cells) + " |")
    zero_support = [label for label in scope if not support.get(label)]
    if zero_support:
        lines += ["", f"No gold span in this split carries {', '.join(zero_support)}, so that class "
                      "can only cost a model false positives and is excluded from the macro above. "
                      "Its per-class row below says what each model predicted for it."]
    lines += ["", "F1 (precision/recall). A class with fewer than ten gold spans is reported "
                  "for completeness; one span either way moves it by more than the differences "
                  "between the models.", ""]
    for result in results:
        run = result["entry"].get("run", {})
        lines.append(f"- **{result['model']}**: `{run.get('model', '?')}`"
                     + (f" at revision `{run.get('revision')}`" if run.get("revision") else "")
                     + (f", phrasing `{run.get('phrasing')}`" if run.get("phrasing") else "")
                     + (f", threshold {result['entry'].get('score_threshold')}"
                        if result["entry"].get("score_threshold") is not None else "")
                     + (f", {result['entry']['note']}" if result["entry"].get("note") else ""))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--data", default="pet_test.json")
    ap.add_argument("--scope", nargs="+", default=PET_SCOPE)
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP_RESAMPLES)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out")
    ap.add_argument("--json")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    results = score_all(spec, args.data, args.scope, args.bootstrap, args.seed)
    text = to_markdown(results, args.data, args.scope)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"\n✅ Wrote {args.out}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ Wrote {args.json}")


if __name__ == "__main__":
    main()
