# The 315-sentence cross-validation under the clean protocol, 2026-11-09, both protocols

The five document-grouped folds of `text2bpmn/baselines/cv_folds.json` (315 sentences: `pet_train.json` minus the 60 development sentences), retrained with the settings the 60 development sentences chose for the models trained on the whole 315-sentence pool:

- BERT: `bert-base-cased`, 8 epochs (`bert_ner_315_dev60`'s selected epoch), the recipe of `text2bpmn/train_ner.py` (no warmup, seed 42 set before the model is created).
- GLiNER A: `urchade/gliner_small-v2.1`, 8 epochs (A-small-v2.1-315's best epoch), threshold 0.85 (chosen on dev, `text2bpmn/baselines/chosen_thresholds_315.json`).

The earlier rerun with the October settings (BERT 9 epochs, warmup 0.1, seed 0; GLiNER 10 epochs, threshold 0.9) is `cv_protocols_315_rerun.md`. CPU only. Predictions, per-fold scores, logs and package versions: `text2bpmn/baselines/cv/clean_315_2026-11-09/`. Scored with `PYTHONPATH=. python3 text2bpmn/baselines/score_cv_protocols.py <folder>`; the per-model outputs are `cv_protocols_clean_315_{bert-base,gliner-small}.json`.

## This project's protocol: strict micro F1 per fold

| Fold | BERT | GLiNER A | GLiNER − BERT | BERT, October settings | GLiNER, October settings |
|---|---|---|---|---|---|
| 0 | 0.577 | 0.740 | +0.163 | 0.599 | 0.753 |
| 1 | 0.758 | 0.865 | +0.107 | 0.762 | 0.857 |
| 2 | 0.578 | 0.686 | +0.108 | 0.579 | 0.699 |
| 3 | 0.663 | 0.777 | +0.114 | 0.665 | 0.810 |
| 4 | 0.670 | 0.759 | +0.089 | 0.644 | 0.773 |
| **mean ± sd** | **0.649 ± 0.075** | **0.765 ± 0.065** | **+0.116 ± 0.028** | 0.650 ± 0.071 | 0.778 ± 0.059 |

Relaxed micro F1: BERT 0.732 ± 0.075, GLiNER A 0.784 ± 0.059, difference +0.052 ± 0.029.

## PET's protocol: one-word relaxation, macro over documents

| Fold | documents | BERT | GLiNER A | GLiNER − BERT |
|---|---|---|---|---|
| 0 | 8 | 0.395 | 0.450 | +0.055 |
| 1 | 8 | 0.453 | 0.481 | +0.028 |
| 2 | 8 | 0.425 | 0.409 | -0.016 |
| 3 | 7 | 0.483 | 0.433 | -0.050 |
| 4 | 7 | 0.587 | 0.541 | -0.046 |
| **mean ± sd** | | **0.469 ± 0.074** | **0.463 ± 0.051** | **-0.006 ± 0.046** |
| range | | 0.395-0.587 | 0.409-0.541 | |

With the October settings: BERT 0.466 ± 0.055, GLiNER A 0.486 ± 0.042, difference +0.020 ± 0.028.

## PET's protocol per type, mean over the five folds

| Type | BERT | GLiNER A |
|---|---|---|
| Actor | 0.802 | 0.872 |
| Activity | 0.707 | 0.856 |
| Activity Data | 0.707 | 0.727 |
| XOR Gateway | 0.681 | 0.595 |
| Condition Specification | 0.316 | 0.190 |
| Further Specification | 0.068 | 0.000 |
| AND Gateway | 0.000 | 0.000 |

## Per-model detail

# bert-base, 5 folds

## This project's protocol (micro over spans)

| Fold | strict F1 | relaxed F1 |
|---|---|---|
| 0 | 0.577 | 0.67 |
| 1 | 0.758 | 0.835 |
| 2 | 0.578 | 0.651 |
| 3 | 0.663 | 0.766 |
| 4 | 0.67 | 0.739 |
| **mean** | **0.649 +/- 0.075** | **0.732 +/- 0.075** |

## PET's protocol (one-word relaxation, macro over documents)

| Fold | documents | macro F1 | AND Gateway | Activity | Activity Data | Actor | Condition Specification | Further Specification | XOR Gateway |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 8 | 0.395 | 0.0 | 0.644 | 0.591 | 0.72 | 0.208 | 0.1 | 0.5 |
| 1 | 8 | 0.453 | 0.0 | 0.737 | 0.773 | 0.852 | 0.125 | 0.0 | 0.683 |
| 2 | 8 | 0.425 | 0.0 | 0.667 | 0.642 | 0.726 | 0.409 | 0.0 | 0.532 |
| 3 | 7 | 0.483 | 0.0 | 0.698 | 0.755 | 0.847 | 0.296 | 0.0 | 0.785 |
| 4 | 7 | 0.587 | 0.0 | 0.787 | 0.774 | 0.864 | 0.544 | 0.238 | 0.905 |
| **mean** | | **0.469 +/- 0.074** | 0.000 | 0.707 | 0.707 | 0.802 | 0.316 | 0.068 | 0.681 |

# gliner-small, 5 folds

## This project's protocol (micro over spans)

| Fold | strict F1 | relaxed F1 |
|---|---|---|
| 0 | 0.74 | 0.769 |
| 1 | 0.865 | 0.869 |
| 2 | 0.686 | 0.71 |
| 3 | 0.777 | 0.807 |
| 4 | 0.759 | 0.767 |
| **mean** | **0.765 +/- 0.065** | **0.784 +/- 0.059** |

## PET's protocol (one-word relaxation, macro over documents)

| Fold | documents | macro F1 | AND Gateway | Activity | Activity Data | Actor | Condition Specification | Further Specification | XOR Gateway |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 8 | 0.45 | 0.0 | 0.815 | 0.66 | 0.875 | 0.261 | 0.0 | 0.538 |
| 1 | 8 | 0.481 | 0.0 | 0.96 | 0.781 | 0.902 | 0.125 | 0.0 | 0.6 |
| 2 | 8 | 0.409 | 0.0 | 0.797 | 0.668 | 0.819 | 0.113 | 0.0 | 0.467 |
| 3 | 7 | 0.433 | 0.0 | 0.854 | 0.755 | 0.898 | 0.057 | 0.0 | 0.464 |
| 4 | 7 | 0.541 | 0.0 | 0.852 | 0.769 | 0.864 | 0.393 | 0.0 | 0.908 |
| **mean** | | **0.463 +/- 0.051** | 0.000 | 0.856 | 0.727 | 0.872 | 0.190 | 0.000 | 0.595 |
