# Entity recognition on pet_test.json

42 sentences, 197 gold spans. Label scope: Activity, Activity Data, Actor, AND Gateway, Condition Specification, Further Specification, XOR Gateway.

Support per class: Activity 62, Activity Data 59, Actor 49, AND Gateway 0, Condition Specification 10, Further Specification 6, XOR Gateway 11.

Micro F1 with a 95% bootstrap interval over the sentences (1000 resamples). A class a model cannot emit is excluded from the bracketed averages.

| Model | strict micro F1 [95% CI] | relaxed micro F1 [95% CI] | strict macro F1 (supported classes) | cannot emit | spans | out-of-scheme spans |
|---|---|---|---|---|---|---|
| BERT ckpt-168 (fine-tuned) | 0.182 [0.124, 0.232] | 0.273 [0.21, 0.33] | 0.116 | AND Gateway, Activity Data, Condition Specification, Further Specification | 182 | TASK_INFO 49 |
| BERT ckpt-564 (fine-tuned) | 0.749 [0.686, 0.809] | 0.824 [0.768, 0.88] | 0.67 | - | 230 | - |
| BERT 315, selected on dev (fine-tuned) | 0.715 [0.64, 0.792] | 0.787 [0.714, 0.856] | 0.644 | - | 220 | - |
| GLiNER medium v2.1 (zero-shot) | 0.11 [0.059, 0.161] | 0.186 [0.126, 0.248] | 0.065 | AND Gateway | 40 | - |
| GLiNER medium v2.5 community (zero-shot) | 0.214 [0.159, 0.267] | 0.361 [0.292, 0.427] | 0.11 | AND Gateway | 196 | - |
| GLiNER2.5 base v1 (zero-shot) | 0.194 [0.137, 0.253] | 0.417 [0.334, 0.505] | 0.108 | AND Gateway | 163 | - |
| GLiNER small v2.1 fine-tuned (315) | 0.849 [0.786, 0.906] | 0.87 [0.816, 0.92] | 0.709 | - | 173 | - |
| GLiNER medium v2.1 fine-tuned (315) | 0.843 [0.787, 0.894] | 0.88 [0.833, 0.923] | 0.705 | - | 178 | - |
| GLiNER small v2.1 fine-tuned, focal loss (315) | 0.861 [0.802, 0.913] | 0.877 [0.83, 0.922] | 0.715 | - | 177 | - |
| GLiNER small v2.1 fine-tuned, hard negatives (315) | 0.802 [0.745, 0.856] | 0.833 [0.78, 0.881] | 0.592 | - | 192 | - |

The table above does not count a span whose predicted class is outside the scheme, which is generous to a model that emits one. Counting those as errors instead:

| Model | strict micro F1 [95% CI] | relaxed micro F1 |
|---|---|---|
| BERT ckpt-168 (fine-tuned) | 0.158 [0.109, 0.201] | 0.237 |

Over the labels each model can emit:

| Model | labels | strict micro F1 [95% CI] | relaxed micro F1 |
|---|---|---|---|
| BERT ckpt-168 (fine-tuned) | Activity, Actor, XOR Gateway | 0.235 [0.166, 0.299] | 0.353 |
| GLiNER medium v2.1 (zero-shot) | Activity, Activity Data, Actor, Condition Specification, Further Specification, XOR Gateway | 0.11 [0.059, 0.161] | 0.186 |
| GLiNER medium v2.5 community (zero-shot) | Activity, Activity Data, Actor, Condition Specification, Further Specification, XOR Gateway | 0.214 [0.159, 0.267] | 0.361 |
| GLiNER2.5 base v1 (zero-shot) | Activity, Activity Data, Actor, Condition Specification, Further Specification, XOR Gateway | 0.194 [0.137, 0.253] | 0.417 |

## Per class, strict

| Class | Support | BERT ckpt-168 (fine-tuned) | BERT ckpt-564 (fine-tuned) | BERT 315, selected on dev (fine-tuned) | GLiNER medium v2.1 (zero-shot) | GLiNER medium v2.5 community (zero-shot) | GLiNER2.5 base v1 (zero-shot) | GLiNER small v2.1 fine-tuned (315) | GLiNER medium v2.1 fine-tuned (315) | GLiNER small v2.1 fine-tuned, focal loss (315) | GLiNER small v2.1 fine-tuned, hard negatives (315) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Activity | 62 | 0.039 (0.033/0.048) | 0.696 (0.632/0.774) | 0.672 (0.613/0.742) | 0.06 (0.4/0.032) | 0.47 (0.402/0.565) | 0.448 (0.481/0.419) | 0.872 (0.927/0.823) | 0.9 (0.931/0.871) | 0.903 (0.903/0.903) | 0.921 (0.906/0.935) |
| Activity Data | 59 | cannot emit | 0.76 (0.7/0.831) | 0.711 (0.694/0.729) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.048 (0.045/0.051) | 0.775 (0.827/0.729) | 0.775 (0.827/0.729) | 0.789 (0.86/0.729) | 0.768 (0.811/0.729) |
| Actor | 49 | 0.659 (0.818/0.551) | 0.904 (0.855/0.959) | 0.874 (0.833/0.918) | 0.328 (0.611/0.224) | 0.189 (0.28/0.143) | 0.15 (0.194/0.122) | 0.96 (0.941/0.98) | 0.902 (0.868/0.939) | 0.949 (0.94/0.959) | 0.932 (0.889/0.98) |
| AND Gateway | 0 | cannot emit | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | cannot emit | cannot emit | cannot emit | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) |
| Condition Specification | 10 | cannot emit | 0.706 (0.857/0.6) | 0.706 (0.857/0.6) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.75 (1.0/0.6) | 0.75 (1.0/0.6) | 0.75 (1.0/0.6) | 0.75 (1.0/0.6) |
| Further Specification | 6 | cannot emit | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.182 (0.2/0.167) |
| XOR Gateway | 11 | 0.0 (0.0/0.0) | 0.952 (1.0/0.909) | 0.9 (1.0/0.818) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.9 (1.0/0.818) | 0.9 (1.0/0.818) | 0.9 (1.0/0.818) | 0.0 (0.0/0.0) |

## Per class, relaxed

| Class | Support | BERT ckpt-168 (fine-tuned) | BERT ckpt-564 (fine-tuned) | BERT 315, selected on dev (fine-tuned) | GLiNER medium v2.1 (zero-shot) | GLiNER medium v2.5 community (zero-shot) | GLiNER2.5 base v1 (zero-shot) | GLiNER small v2.1 fine-tuned (315) | GLiNER medium v2.1 fine-tuned (315) | GLiNER small v2.1 fine-tuned, focal loss (315) | GLiNER small v2.1 fine-tuned, hard negatives (315) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Activity | 62 | 0.211 (0.178/0.258) | 0.855 (0.776/0.952) | 0.832 (0.76/0.919) | 0.09 (0.6/0.048) | 0.483 (0.414/0.581) | 0.466 (0.5/0.435) | 0.889 (0.945/0.839) | 0.933 (0.966/0.903) | 0.919 (0.919/0.919) | 0.952 (0.938/0.968) |
| Activity Data | 59 | cannot emit | 0.822 (0.757/0.898) | 0.76 (0.742/0.78) | 0.058 (0.2/0.034) | 0.221 (0.195/0.254) | 0.444 (0.418/0.475) | 0.829 (0.885/0.78) | 0.865 (0.923/0.814) | 0.826 (0.9/0.763) | 0.839 (0.887/0.797) |
| Actor | 49 | 0.707 (0.879/0.592) | 0.923 (0.873/0.98) | 0.893 (0.852/0.939) | 0.507 (0.944/0.347) | 0.514 (0.76/0.388) | 0.5 (0.645/0.408) | 0.96 (0.941/0.98) | 0.902 (0.868/0.939) | 0.949 (0.94/0.959) | 0.932 (0.889/0.98) |
| AND Gateway | 0 | cannot emit | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | cannot emit | cannot emit | cannot emit | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) |
| Condition Specification | 10 | cannot emit | 0.706 (0.857/0.6) | 0.706 (0.857/0.6) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.75 (1.0/0.6) | 0.75 (1.0/0.6) | 0.75 (1.0/0.6) | 0.75 (1.0/0.6) |
| Further Specification | 6 | cannot emit | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.25 (0.5/0.167) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.182 (0.2/0.167) |
| XOR Gateway | 11 | 0.0 (0.0/0.0) | 0.952 (1.0/0.909) | 0.9 (1.0/0.818) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.0 (0.0/0.0) | 0.9 (1.0/0.818) | 0.9 (1.0/0.818) | 0.9 (1.0/0.818) | 0.0 (0.0/0.0) |

No gold span in this split carries AND Gateway, so that class can only cost a model false positives and is excluded from the macro above. Its per-class row below says what each model predicted for it.

F1 (precision/recall). A class with fewer than ten gold spans is reported for completeness; one span either way moves it by more than the differences between the models.

- **BERT ckpt-168 (fine-tuned)**: `./process-visualizer/src/token_classification_alex/my_final_benchmark/checkpoint-168`, the checkpoint the published pipeline used; 4 label types
- **BERT ckpt-564 (fine-tuned)**: `./process-visualizer/src/token_classification_alex/my_final_benchmark/checkpoint-564`, trained on all 375 sentences; early stopping and epoch chosen on the held-out split
- **BERT 315, selected on dev (fine-tuned)**: `process-visualizer/src/token_classification_alex/bert_ner_315_dev60`, text2bpmn/train_ner.py: 315 sentences, epoch chosen on the 60 development sentences
- **GLiNER medium v2.1 (zero-shot)**: `urchade/gliner_medium-v2.1` at revision `40ec419335d09393f298636f471328b722c6da9e`, phrasing `scheme`, threshold 0.3, phrasing and threshold chosen on dev
- **GLiNER medium v2.5 community (zero-shot)**: `gliner-community/gliner_medium-v2.5` at revision `88c3b98b57ad5e7d66fb209ed61c53f4b1fd05da`, phrasing `scheme`, threshold 0.3, phrasing and threshold chosen on dev
- **GLiNER2.5 base v1 (zero-shot)**: `fastino/gliner2.5-base-v1` at revision `ca906247640776a07753514055be9726f9080ead`, phrasing `scheme`, threshold 0.3, phrasing and threshold chosen on dev
- **GLiNER small v2.1 fine-tuned (315)**: `text2bpmn/baselines/finetuned_315/A-small-v2.1-315/best` at revision `unknown (HFValidationError)`, phrasing `identity`, threshold 0.85, 315 sentences; threshold 0.85 chosen on dev (dev strict F1 0.842)
- **GLiNER medium v2.1 fine-tuned (315)**: `text2bpmn/baselines/finetuned_315/B-medium-v2.1-315/best` at revision `unknown (HFValidationError)`, phrasing `identity`, threshold 0.95, 315 sentences; threshold 0.95 chosen on dev (dev strict F1 0.825)
- **GLiNER small v2.1 fine-tuned, focal loss (315)**: `text2bpmn/baselines/finetuned_315/C-small-focal-315/best` at revision `unknown (HFValidationError)`, phrasing `identity`, threshold 0.75, 315 sentences; threshold 0.75 chosen on dev (dev strict F1 0.817)
- **GLiNER small v2.1 fine-tuned, hard negatives (315)**: `text2bpmn/baselines/finetuned_315/D-small-hardneg-315/best` at revision `unknown (HFValidationError)`, phrasing `identity`, threshold 0.75, 315 sentences; threshold 0.75 chosen on dev (dev strict F1 0.806)
