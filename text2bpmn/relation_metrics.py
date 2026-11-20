"""Relation-extraction metrics from a stored benchmark run (ticket C1).

    python3 -m text2bpmn.relation_metrics --dataset benchmark_silver_2.jsonl \
        --report benchmark_results_silver_fewshot_final2.md [--model dspy|bert] \
        [--json OUT.json] [--figure OUT.png]

The confusion matrix and the per-class table use one explicit label order,
LABELS, passed to every sklearn call and to the figure, so a row can never be
paired with the wrong class. A prediction outside LABELS (UNKNOWN, from a parse
failure) is kept: it counts as an error and gets its own matrix column.

Predictions are rebuilt from the report benchmark_relations.py writes. That
report lists every sample on which either model was wrong, with both models'
predictions, so every unlisted sample was predicted correctly by both. Listed
rows are matched to their exact sample by the (entity_1, entity_2) pair, which
is unique in the benchmark.
"""
import argparse
import json
from pathlib import Path

# scikit-learn is imported where the metrics are computed, not here: this
# module is imported for LABELS alone by text2bpmn/relation_parsing.py, which
# the pipeline needs on machines that score nothing (text2bpmn/remote/)
LABELS = ["SEQUENCE", "TRUE_BRANCH", "FALSE_BRANCH", "PARALLEL", "CONDITION_DEF"]
MODEL_COLUMN = {"bert": 3, "dspy": 4}  # cell index after the leading "|"


def load_dataset(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def predictions_from_report(report_path, samples, model="dspy"):
    index = {(s["entity_1"], s["entity_2"]): i for i, s in enumerate(samples)}
    preds = [s["label"] for s in samples]
    rows = [line for line in Path(report_path).read_text(encoding="utf-8").splitlines()
            if line.startswith("| ") and "->" in line and "**" in line]
    for line in rows:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        pair, truth, predicted = cells[1], cells[2].strip("*"), cells[MODEL_COLUMN[model]]
        key = next(((pair[:k], pair[k + 4:]) for k in range(len(pair)) if pair.startswith(" -> ", k)
                    and (pair[:k], pair[k + 4:]) in index), None)
        if key is None:
            raise ValueError(f"report row matches no benchmark sample: {pair!r}")
        i = index[key]
        if samples[i]["label"] != truth:
            raise ValueError(f"ground truth differs for {pair!r}: {truth} vs {samples[i]['label']}")
        preds[i] = predicted.replace("✅", "").replace("❌", "").strip()
    return preds


def compute(y_true, y_pred, labels=LABELS):
    extra = sorted(set(y_pred) - set(labels))
    columns = list(labels) + extra
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    matrix = confusion_matrix(y_true, y_pred, labels=columns)[:len(labels)]
    p, r, f, support = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    n = len(y_true)
    correct = sum(t == q for t, q in zip(y_true, y_pred))
    total = support.sum()
    return {
        "n": n,
        "correct": correct,
        "accuracy": correct / n,
        "labels": list(labels),
        "predicted_columns": columns,
        "confusion_matrix": matrix.tolist(),  # rows: true label (labels); columns: predicted_columns
        "per_class": {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                          "support": int(support[i])} for i, c in enumerate(labels)},
        "macro_f1": float(f.mean()),
        "weighted_f1": float((f * support).sum() / total) if total else 0.0,
    }


def to_markdown(res):
    out = [f"Accuracy {res['accuracy']:.3f} ({res['correct']}/{res['n']}), "
           f"weighted F1 {res['weighted_f1']:.3f}, macro F1 {res['macro_f1']:.3f}", "",
           "| Relation | Precision | Recall | F1 | Support |", "| --- | --- | --- | --- | --- |"]
    for c, m in res["per_class"].items():
        out.append(f"| {c} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['support']} |")
    out += ["", "| true \\ predicted | " + " | ".join(res["predicted_columns"]) + " |",
            "| --- " * (len(res["predicted_columns"]) + 1) + "|"]
    for c, row in zip(res["labels"], res["confusion_matrix"]):
        out.append(f"| {c} | " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(out)


def plot_confusion(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.imshow(res["confusion_matrix"], cmap="Blues")
    ax.set_xticks(range(len(res["predicted_columns"])), res["predicted_columns"], rotation=45, ha="right")
    ax.set_yticks(range(len(res["labels"])), res["labels"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    peak = max(max(row) for row in res["confusion_matrix"])
    for i, row in enumerate(res["confusion_matrix"]):
        for j, v in enumerate(row):
            ax.text(j, i, v, ha="center", va="center", color="white" if v > peak / 2 else "black")
    fig.tight_layout()
    fig.savefig(path, dpi=200)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--model", choices=sorted(MODEL_COLUMN), default="dspy")
    ap.add_argument("--json")
    ap.add_argument("--figure")
    args = ap.parse_args()
    samples = load_dataset(args.dataset)
    res = compute([s["label"] for s in samples], predictions_from_report(args.report, samples, args.model))
    print(to_markdown(res))
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=2))
    if args.figure:
        plot_confusion(res, args.figure)


if __name__ == "__main__":
    main()
