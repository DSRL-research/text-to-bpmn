"""The comparison spec for the models trained on the 315-sentence pool.

    PYTHONPATH=. python3 text2bpmn/baselines/build_comparison_315.py

As build_comparison.py, for the models of 2026-11-09: BERT trained by
text2bpmn/train_ner.py and the four GLiNER configurations of train_all_315.sh,
all trained on text2bpmn/baselines/train_315.json and selected on the 60
development sentences only. Each GLiNER threshold is chosen on dev from spans
already saved; nothing here runs a model, so the held-out split stays at one
pass per model. The zero-shot rows and checkpoints 168 and 564 are carried
over unchanged for comparison; 564 was selected on the held-out split itself.

Writes comparison_spec_315.json and chosen_thresholds_315.json.
"""
import json
from pathlib import Path

from text2bpmn.gliner_baseline import best, sweep

B = Path("text2bpmn/baselines")
DEV = B / "dev_split.json"
FINE_TUNED_RANGE = [round(0.30 + 0.05 * i, 2) for i in range(14)]   # 0.30 .. 0.95, as before

FINE_TUNED = [
    ("A-small-v2.1-315", "GLiNER small v2.1 fine-tuned (315)"),
    ("B-medium-v2.1-315", "GLiNER medium v2.1 fine-tuned (315)"),
    ("C-small-focal-315", "GLiNER small v2.1 fine-tuned, focal loss (315)"),
    ("D-small-hardneg-315", "GLiNER small v2.1 fine-tuned, hard negatives (315)"),
]

old = {entry["name"]: entry for entry in json.loads((B / "comparison_spec.json").read_text(encoding="utf-8"))}
spec = [dict(old["BERT ckpt-168 (fine-tuned)"]),
        dict(old["BERT ckpt-564 (fine-tuned)"],
             note="trained on all 375 sentences; early stopping and epoch chosen on the held-out split"),
        {"name": "BERT 315, selected on dev (fine-tuned)", "spans": str(B / "test_bert_315_dev60.json"),
         "note": "text2bpmn/train_ner.py: 315 sentences, epoch chosen on the 60 development sentences"}]
spec += [dict(entry) for name, entry in old.items() if "zero-shot" in name]

chosen = {}
for name, label in FINE_TUNED:
    dev_spans, test_spans = B / f"dev_ft_{name}.json", B / f"TEST_ft_{name}.json"
    if not (dev_spans.exists() and test_spans.exists()):
        print(f"skipping {name}: no spans yet")
        continue
    winner = best(sweep(DEV, [str(dev_spans)], FINE_TUNED_RANGE))
    chosen[name] = winner
    print(f"{name:20} dev threshold {winner['threshold']} -> dev strict {winner['strict_micro_f1']}")
    spec.append({"name": label, "spans": str(test_spans), "score_threshold": winner["threshold"],
                 "note": f"315 sentences; threshold {winner['threshold']} chosen on dev "
                         f"(dev strict F1 {winner['strict_micro_f1']})"})

(B / "comparison_spec_315.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
(B / "chosen_thresholds_315.json").write_text(json.dumps(chosen, indent=2), encoding="utf-8")
print(f"\n{len(spec)} rows -> {B / 'comparison_spec_315.json'}")
