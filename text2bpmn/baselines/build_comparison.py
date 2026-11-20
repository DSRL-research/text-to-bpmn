"""Choose each fine-tuned model's threshold on dev, then write the comparison spec.

    python3 text2bpmn/baselines/build_comparison.py

Nothing here runs a model: every threshold is applied to spans already saved,
which is what keeps the held-out split to one pass per configuration.
"""
import json
from pathlib import Path

from text2bpmn.gliner_baseline import best, sweep

B = Path("text2bpmn/baselines")
DEV = B / "dev_split.json"
# a fine-tuned model is confident, so its threshold sits above the range the
# zero-shot sweep was specified over; the range is extended for those rows only
FINE_TUNED_RANGE = [round(0.30 + 0.05 * i, 2) for i in range(14)]   # 0.30 .. 0.95
ZERO_SHOT_RANGE = [round(0.30 + 0.05 * i, 2) for i in range(9)]     # 0.30 .. 0.70

FINE_TUNED = [
    ("A-small-v2.1", "GLiNER small v2.1 fine-tuned"),
    ("B-medium-v2.1", "GLiNER medium v2.1 fine-tuned"),
    ("C-small-focal", "GLiNER small v2.1 fine-tuned, focal loss"),
    ("D-small-hardneg", "GLiNER small v2.1 fine-tuned, hard negatives"),
]

spec = [
    {"name": "BERT ckpt-168 (fine-tuned)",
     "spans": str(B / "test_bert_checkpoint-168.json"),
     "note": "the checkpoint the published pipeline used; 4 label types"},
    {"name": "BERT ckpt-564 (fine-tuned)",
     "spans": str(B / "test_bert_checkpoint-564.json"),
     "note": "the checkpoint the corrected pipeline uses; 7 label types"},
]
for tag, repo, label in (("v2.1", "urchade/gliner_medium-v2.1", "GLiNER medium v2.1 (zero-shot)"),
                         ("v2.5community", "gliner-community/gliner_medium-v2.5",
                          "GLiNER medium v2.5 community (zero-shot)"),
                         ("gliner25base", "fastino/gliner2.5-base-v1",
                          "GLiNER2.5 base v1 (zero-shot)")):
    spans = B / f"TEST_{tag}_scheme.json"
    if spans.exists():
        spec.append({"name": label, "spans": str(spans), "score_threshold": 0.3,
                     "note": "phrasing and threshold chosen on dev"})

chosen = {}
for name, label in FINE_TUNED:
    dev_spans, test_spans = B / f"dev_ft_{name}.json", B / f"TEST_ft_{name}.json"
    if not (dev_spans.exists() and test_spans.exists()):
        print(f"skipping {name}: no spans yet")
        continue
    rows = sweep(DEV, [str(dev_spans)], FINE_TUNED_RANGE)
    winner = best(rows)
    chosen[name] = winner
    print(f"{name:18} dev threshold {winner['threshold']} -> dev strict "
          f"{winner['strict_micro_f1']}")
    spec.append({"name": label, "spans": str(test_spans),
                 "score_threshold": winner["threshold"],
                 "note": f"threshold {winner['threshold']} chosen on dev "
                         f"(dev strict F1 {winner['strict_micro_f1']})"})

(B / "comparison_spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
(B / "chosen_thresholds.json").write_text(json.dumps(chosen, indent=2), encoding="utf-8")
print(f"\n{len(spec)} rows -> {B / 'comparison_spec.json'}")
