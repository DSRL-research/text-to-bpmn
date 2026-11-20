# 315-sentence cross-validation, clean protocol, 2026-11-09

The five document-grouped folds of `text2bpmn/baselines/cv_folds.json` (315 sentences:
`pet_train.json` minus the 60 development sentences), trained with the settings the development
sentences chose for the models trained on the whole 315-sentence pool:

- `bert-base/`: `bert-base-cased`, 8 epochs (the epoch `text2bpmn/train_ner.py` selected for
  `bert_ner_315_dev60`), no warmup, seed 42 set before the model is created
  (`--warmup-ratio 0 --seed 42 --seed-model`)
- `gliner-small/`: `urchade/gliner_small-v2.1`, 8 epochs (A-small-v2.1-315's best epoch on dev),
  threshold 0.85 (chosen on dev, `../../chosen_thresholds_315.json`)

`../rerun_315_2026-11-09/` holds the same folds with the October settings.

- `*/cv.json`, `*/folds.json`: per-fold scores as written by `text2bpmn/cross_validate.py`
- `*/predictions_fold*.json`: gold and predicted spans per held-out sentence
- `bert.log`, `gliner.log`, `times.txt`: the run's output and start/end times
- `versions.json`: code, package versions of both environments, base-model revisions, commands,
  hardware (CPU only)

Scores under both protocols: `text2bpmn/results/cv_protocols_clean_315.md`.
