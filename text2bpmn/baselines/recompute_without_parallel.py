import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from text2bpmn.guardrails import false_branch_guardrail
from text2bpmn.relation_metrics import LABELS, load_dataset, predictions_from_report

def metrics(y_true, y_pred, labels):
    """Accuracy, per-class P/R/F1, macro and weighted F1. Plain definitions."""
    per = {}
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[lab] = {"p": prec, "r": rec, "f1": f1, "support": tp + fn}
    n = len(y_true)
    correct = sum(t == p for t, p in zip(y_true, y_pred))
    total = sum(v["support"] for v in per.values())
    return {"n": n, "correct": correct, "accuracy": correct / n, "per_class": per,
            "macro_f1": sum(v["f1"] for v in per.values()) / len(per),
            "weighted_f1": sum(v["f1"] * v["support"] for v in per.values()) / total}

samples = load_dataset("benchmark_silver_2.jsonl")
truth = [s["label"] for s in samples]
preds, raws = {}, {}
for model in ("bert", "dspy"):
    raws[model] = predictions_from_report("benchmark_results_silver_fewshot_final2.md", samples, model)
    preds[model] = [false_branch_guardrail(p, s["entity_1"], s["entity_2"], "entity_1")
                    for s, p in zip(samples, raws[model])]

keep = [i for i, t in enumerate(truth) if t != "PARALLEL"]
sub_labels = [l for l in LABELS if l != "PARALLEL"]

print("=== all 302 pairs, corrected entity_1 guardrail (the published figures) ===")
for m in ("bert", "dspy"):
    r = metrics(truth, preds[m], LABELS)
    print(f"  {m:5} accuracy {r['accuracy']:.3f} ({r['correct']}/{r['n']})"
          f"   macro F1 {r['macro_f1']:.3f}   weighted F1 {r['weighted_f1']:.3f}")

print(f"\n=== the {len(keep)} pairs whose true label is not PARALLEL ===")
res_sub = {}
for m in ("bert", "dspy"):
    yt = [truth[i] for i in keep]; yp = [preds[m][i] for i in keep]
    res_sub[m] = metrics(yt, yp, sub_labels)
    r = res_sub[m]
    print(f"  {m:5} accuracy {r['accuracy']:.3f} ({r['correct']}/{r['n']})"
          f"   macro F1 {r['macro_f1']:.3f}   weighted F1 {r['weighted_f1']:.3f}"
          f"   still predicted PARALLEL on {sum(1 for p in yp if p == 'PARALLEL')}")

res_full = {m: metrics(truth, preds[m], LABELS) for m in ("bert", "dspy")}
print("\n=== per-class F1 ===")
print(f"{'label':15}{'BERT 302':>10}{'BERT 256':>10}{'DSPy 302':>10}{'DSPy 256':>10}{'support':>9}")
for lab in LABELS:
    cells = ""
    for m in ("bert", "dspy"):
        cells += f"{res_full[m]['per_class'][lab]['f1']:10.3f}"
        cells += f"{res_sub[m]['per_class'][lab]['f1']:10.3f}" if lab in sub_labels else f"{'--':>10}"
    print(f"{lab:15}{cells}{res_full['bert']['per_class'][lab]['support']:9}")
