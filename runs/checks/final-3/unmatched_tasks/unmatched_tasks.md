# Unmatched tasks in the case studies

Run 2026-11-20T08:19:35+00:00 at revision-final-3-76-g99107f3 (99107f3, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Run `runs/final-3/cases`. Matcher: text2bpmn.compare as it is. Tasks are matched one-to-one by an optimal assignment (scipy linear_sum_assignment, text2bpmn/compare.py:154) on compare.similarity (text2bpmn/compare.py:129): the largest of the character ratio, the ratio with words sorted, and the overlap of five-character word stems, on lower-cased labels without punctuation or articles. A pair counts as matched when its score is at least the threshold DEFAULT_THRESHOLD = 0.5 (text2bpmn/compare.py:37, tested at text2bpmn/compare.py:155); the run called compare() with the default (text2bpmn/run_final.py:161).
scipy and numpy here: {'scipy': '1.16.2', 'numpy': '1.26.4'}; in the run (`runs/final-3/pip_freeze.txt`): {'numpy': '1.26.4', 'scipy': '1.16.2'}.

| case | reference tasks | generated tasks | TP | FP | FN | reproduces comparison.json |
|---|---|---|---|---|---|---|
| healthcare | 23 | 32 | 17 | 15 | 6 | True |
| goods_dispatch | 7 | 10 | 5 | 5 | 2 | True |

## healthcare

Generated `runs/final-3/cases/healthcare/model.bpmn` (run at revision-final-3, 808815f; LLM hosted_vllm/Qwen/Qwen3.5-27B-FP8, no-LLM False, relation mode decisions4, NER `./process-visualizer/src/token_classification_alex/bert_ner_315_dev60`).
Reference `text2bpmn/cases/healthcare/reference.bpmn` (sha256 f4c2538a2708; the same file as the one the run scored against, `text2bpmn/cases/healthcare/reference.bpmn` at 808815f: False).
23 reference tasks, 32 generated tasks, 17 matched at threshold 0.5.

| task counts | TP | FP | FN |
|---|---|---|---|
| saved, `runs/final-3/cases/healthcare/comparison.json` | 17 | 15 | 6 |
| compare() now | 17 | 15 | 6 |
| the lists below | 17 | 15 | 6 |

Counts reproduce comparison.json: True; mapping: True; unmatched reference names: True; unmatched generated names: True.

### Unmatched, side by side

The two lists are in model order; a row does not pair the two sides. Best score: the highest compare.similarity the generated task reaches against any reference task.

| # | Reference task not matched | Generated task not matched | Best score | Best reference task | Already matched? |
|---|---|---|---|---|---|
| 1 | Present Directly to ED | Develops | 0.385 | Perform Evaluation | yes, to 'Evaluates' (0.667) |
| 2 | Family Calls 112 | Contacts | 0.333 | Maintain Communication | yes, to 'Maintains' (0.667) |
| 3 | Refer to Outpatient Cardiologist | Presents | 0.467 | Present Directly to ED | no |
| 4 | Complete Treatment | Make a triage decision | 0.476 | Maintain Communication | yes, to 'Maintains' (0.667) |
| 5 | Surgical Treatment | Managed | 0.333 | Prepare the discharge | yes, to 'Prepares the discharge' (1.000) |
| 6 | Medical Treatment | Referred | 0.400 | Present Directly to ED / Refer to Outpatient Cardiologist / Prepare the discharge | no / no / yes, to 'Prepares the discharge' (1.000) |
| 7 |  | Takes the | 0.273 | Patient Calls 112 | yes, to 'Discharge patient's' (0.556) |
| 8 |  | Initiates | 0.500 | Adjust/Initiate Treatment | yes, to 'Adjusts' (0.500) |
| 9 |  | Choose | 0.294 | Consult Private Cardiologist | yes, to 'Consult route' (0.537) |
| 10 |  | Decide | 0.345 | Provide medical history | yes, to 'Provides the medical history' (1.000) |
| 11 |  | Gathered medical history | 0.766 | Provide medical history | yes, to 'Provides the medical history' (1.000) |
| 12 |  | Administers the | 0.471 | Family Provides History | yes, to 'Provides history' (0.821) |
| 13 |  | Inform | 0.500 | Perform Evaluation | yes, to 'Evaluates' (0.667) |
| 14 |  | Follow-up a | 0.381 | Prescribe Treatment and Followups | yes, to 'Prescribes treatment' (0.717) |
| 15 |  | Concludes the | 0.333 | Provide Summary | yes, to 'Gives a discharge summary' (0.579) |

No unmatched generated task reaches the threshold against an unmatched reference task.

### Unmatched reference tasks: nearest generated task

| Reference task | Best score | Best generated task | Already matched? | Assigned below the threshold to |
|---|---|---|---|---|
| Present Directly to ED | 0.522 | Provides the medical history | yes, to 'Provide medical history' (1.000) | Presents (0.467) |
| Family Calls 112 | 0.372 | Establishes the final diagnosis | yes, to 'Establish Final Diagnosis' (1.000) | Follow-up a (0.320) |
| Refer to Outpatient Cardiologist | 0.510 | Discharge patient's | yes, to 'Patient Calls 112' (0.556) | Referred (0.400) |
| Complete Treatment | 0.632 | Prescribes treatment | yes, to 'Prescribe Treatment and Followups' (0.717) | Make a triage decision (0.421) |
| Surgical Treatment | 0.684 | Prescribes treatment | yes, to 'Prescribe Treatment and Followups' (0.717) | Initiates (0.370) |
| Medical Treatment | 0.649 | Prescribes treatment | yes, to 'Prescribe Treatment and Followups' (0.717) | Gathered medical history (0.488) |

### Unmatched generated tasks: the assignment's partner

| Generated task | Assigned below the threshold to |
|---|---|
| Develops | none (more generated than reference tasks) |
| Contacts | none (more generated than reference tasks) |
| Presents | Present Directly to ED (0.467) |
| Make a triage decision | Complete Treatment (0.421) |
| Managed | none (more generated than reference tasks) |
| Referred | Refer to Outpatient Cardiologist (0.400) |
| Takes the | none (more generated than reference tasks) |
| Initiates | Surgical Treatment (0.370) |
| Choose | none (more generated than reference tasks) |
| Decide | none (more generated than reference tasks) |
| Gathered medical history | Medical Treatment (0.488) |
| Administers the | none (more generated than reference tasks) |
| Inform | none (more generated than reference tasks) |
| Follow-up a | Family Calls 112 (0.320) |
| Concludes the | none (more generated than reference tasks) |

### Matched pairs

| Reference task | Generated task | Score |
|---|---|---|
| Adjust/Initiate Treatment | Adjusts | 0.500 |
| Admit Urgent Hospitalization | Admit | 0.500 |
| Submit summary to GP | Submits | 0.519 |
| Visit GP | Sets up | 0.533 |
| Consult Private Cardiologist | Consult route | 0.537 |
| Patient Calls 112 | Discharge patient's | 0.556 |
| Provide Summary | Gives a discharge summary | 0.579 |
| Evaluate Patient | Recommend patient | 0.606 |
| Interventional Treatment | Discharge treatment recommendations | 0.644 |
| Perform Evaluation | Evaluates | 0.667 |
| Maintain Communication | Maintains | 0.667 |
| Prescribe Treatment and Followups | Prescribes treatment | 0.717 |
| Recommend Cardiological Evaluation | Recommends specialized evaluation | 0.746 |
| Family Provides History | Provides history | 0.821 |
| Provide medical history | Provides the medical history | 1.000 |
| Establish Final Diagnosis | Establishes the final diagnosis | 1.000 |
| Prepare the discharge | Prepares the discharge | 1.000 |

## goods_dispatch

Generated `runs/final-3/cases/goods_dispatch/model.bpmn` (run at revision-final-3, 808815f; LLM hosted_vllm/Qwen/Qwen3.5-27B-FP8, no-LLM False, relation mode decisions4, NER `./process-visualizer/src/token_classification_alex/bert_ner_315_dev60`).
Reference `text2bpmn/cases/goods_dispatch/reference.bpmn` (sha256 bae9ed647ee8; the same file as the one the run scored against, `text2bpmn/cases/goods_dispatch/reference.bpmn` at 808815f: True).
7 reference tasks, 10 generated tasks, 5 matched at threshold 0.5.

| task counts | TP | FP | FN |
|---|---|---|---|
| saved, `runs/final-3/cases/goods_dispatch/comparison.json` | 5 | 5 | 2 |
| compare() now | 5 | 5 | 2 |
| the lists below | 5 | 5 | 2 |

Counts reproduce comparison.json: True; mapping: True; unmatched reference names: True; unmatched generated names: True.

### Unmatched, side by side

The two lists are in model order; a row does not pair the two sides. Best score: the highest compare.similarity the generated task reaches against any reference task.

| # | Reference task not matched | Generated task not matched | Best score | Best reference task | Already matched? |
|---|---|---|---|---|---|
| 1 | Get 3 offers from logistic companies | Invites | 0.300 | Insure parcel | yes, to 'Taken a parcel insurance' (0.800) |
| 2 | Select logistic company and place order | Make offers | 0.500 | Package goods | yes, to 'Packaged the goods' (1.000) |
| 3 |  | Selects one | 0.417 | Insure parcel | yes, to 'Taken a parcel insurance' (0.800) |
| 4 |  | Used post | 0.364 | Insure parcel | yes, to 'Taken a parcel insurance' (0.800) |
| 5 |  | Picked up | 0.455 | Package goods | yes, to 'Packaged the goods' (1.000) |

No unmatched generated task reaches the threshold against an unmatched reference task.

### Unmatched reference tasks: nearest generated task

| Reference task | Best score | Best generated task | Already matched? | Assigned below the threshold to |
|---|---|---|---|---|
| Get 3 offers from logistic companies | 0.426 | Make offers | no | Make offers (0.426) |
| Select logistic company and place order | 0.400 | Selects one | no | Selects one (0.400) |

### Unmatched generated tasks: the assignment's partner

| Generated task | Assigned below the threshold to |
|---|---|
| Invites | none (more generated than reference tasks) |
| Make offers | Get 3 offers from logistic companies (0.426) |
| Selects one | Select logistic company and place order (0.400) |
| Used post | none (more generated than reference tasks) |
| Picked up | none (more generated than reference tasks) |

### Matched pairs

| Reference task | Generated task | Score |
|---|---|---|
| Clarify shipment method | Clarifies shipping | 0.634 |
| Prepare for picking up goods | Prepared the packaged goods | 0.706 |
| Insure parcel | Taken a parcel insurance | 0.800 |
| Write package label | Written a package label | 0.950 |
| Package goods | Packaged the goods | 1.000 |
