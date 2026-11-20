"""Paired bootstrap differences on the held-out split, for the 315-sentence models.

    PYTHONPATH=. python3 text2bpmn/baselines/paired_bootstrap_315.py

Both models of a pair are rescored on the same resample of the 42 sentences
(eval_ner.bootstrap_difference, 1000 resamples, seed 0, the seven PET labels).
Only saved spans are read: nothing runs a model, and each GLiNER threshold is
the one chosen on dev (chosen_thresholds_315.json, chosen_thresholds.json).
The last pair is the October comparison, kept as a check that the procedure
reproduces it.

Writes text2bpmn/results/ner_paired_bootstrap_315.json and .md.
"""
import json
from pathlib import Path

from text2bpmn.eval_ner import bootstrap_difference, load_pet, load_predictions
from text2bpmn.ner_comparison import PET_SCOPE

B = Path("text2bpmn/baselines")
R = Path("text2bpmn/results")
DATA = "pet_test.json"
RESAMPLES, SEED = 1000, 0

new_t = json.loads((B / "chosen_thresholds_315.json").read_text())["A-small-v2.1-315"]["threshold"]
old_t = json.loads((B / "chosen_thresholds.json").read_text())["A-small-v2.1"]["threshold"]
MODELS = {
    "GLiNER A (315)": (B / "TEST_ft_A-small-v2.1-315.json", new_t),
    "BERT (315)": (B / "test_bert_315_dev60.json", None),
    "GLiNER A (375)": (B / "TEST_ft_A-small-v2.1.json", old_t),
    "BERT checkpoint-564 (375)": (B / "test_bert_checkpoint-564.json", None),
}
PAIRS = [("GLiNER A (315)", "BERT (315)"),
         ("BERT (315)", "BERT checkpoint-564 (375)"),
         ("GLiNER A (315)", "GLiNER A (375)"),
         ("GLiNER A (375)", "BERT checkpoint-564 (375)")]

gold = load_pet(DATA)


def documents(name):
    path, threshold = MODELS[name]
    predicted = load_predictions(path, len(gold), threshold)
    return [(sentence[1], spans) for sentence, spans in zip(gold, predicted)]


results = []
for first, second in PAIRS:
    row = {"first": first, "second": second,
           "first_spans": str(MODELS[first][0]), "first_threshold": MODELS[first][1],
           "second_spans": str(MODELS[second][0]), "second_threshold": MODELS[second][1]}
    for criterion in ("strict", "relaxed"):
        row[criterion] = bootstrap_difference(documents(first), documents(second), criterion,
                                              scope=PET_SCOPE, resamples=RESAMPLES, seed=SEED)
    results.append(row)

lines = ["# Paired bootstrap, micro F1 on pet_test.json", "",
         f"First minus second, both rescored on the same {RESAMPLES} resamples of the 42 sentences "
         f"(seed {SEED}); 95% percentile interval; labels: {', '.join(PET_SCOPE)}. GLiNER thresholds "
         f"chosen on dev: {new_t} (315), {old_t} (375). Written by "
         "text2bpmn/baselines/paired_bootstrap_315.py from saved spans.", "",
         "| first | second | strict difference [95% CI] | resamples favouring first | "
         "relaxed difference [95% CI] | resamples favouring first |",
         "|---|---|---|---|---|---|"]
for row in results:
    s, r = row["strict"], row["relaxed"]
    lines.append(f"| {row['first']} | {row['second']} | {s['difference']:+.3f} "
                 f"[{s['ci95_low']:+.3f}, {s['ci95_high']:+.3f}] | {s['resamples_favouring_first']} | "
                 f"{r['difference']:+.3f} [{r['ci95_low']:+.3f}, {r['ci95_high']:+.3f}] | "
                 f"{r['resamples_favouring_first']} |")
lines += ["", "The last row is the October comparison (both models trained on all 375 sentences; "
          "checkpoint-564 selected on this split), kept to check the procedure."]
(R / "ner_paired_bootstrap_315.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
(R / "ner_paired_bootstrap_315.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
