# Unmatched tasks in the case studies

Run 2026-11-20T08:19:52+00:00 at revision-final-3-76-g99107f3 (99107f3, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Run `runs/final-3/cases`. Matcher: text2bpmn.compare as it is. Tasks are matched one-to-one by an optimal assignment (scipy linear_sum_assignment, text2bpmn/compare.py:154) on compare.similarity (text2bpmn/compare.py:129): the largest of the character ratio, the ratio with words sorted, and the overlap of five-character word stems, on lower-cased labels without punctuation or articles. A pair counts as matched when its score is at least the threshold DEFAULT_THRESHOLD = 0.5 (text2bpmn/compare.py:37, tested at text2bpmn/compare.py:155); the run called compare() with the default (text2bpmn/run_final.py:161).
scipy and numpy here: {'scipy': '1.16.2', 'numpy': '1.26.4'}; in the run (`runs/final-3/pip_freeze.txt`): {'numpy': '1.26.4', 'scipy': '1.16.2'}.

| case | reference tasks | generated tasks | TP | FP | FN | reproduces comparison.json |
|---|---|---|---|---|---|---|
| loan | 7 | 6 | 4 | 2 | 3 | True |

## loan

Generated `runs/final-3/cases/loan/model.bpmn` (run at revision-final-3, 808815f; LLM hosted_vllm/Qwen/Qwen3.5-27B-FP8, no-LLM False, relation mode decisions4, NER `./process-visualizer/src/token_classification_alex/bert_ner_315_dev60`).
Reference `text2bpmn/cases/loan/reference.bpmn` (sha256 5bdbccee7795; the same file as the one the run scored against, `text2bpmn/cases/loan/reference.bpmn` at 808815f: False).
7 reference tasks, 6 generated tasks, 4 matched at threshold 0.5.

| task counts | TP | FP | FN |
|---|---|---|---|
| saved, `runs/final-3/cases/loan/comparison.json` | 4 | 2 | 3 |
| compare() now | 4 | 2 | 3 |
| the lists below | 4 | 2 | 3 |

Counts reproduce comparison.json: True; mapping: True; unmatched reference names: True; unmatched generated names: True.

### Unmatched, side by side

The two lists are in model order; a row does not pair the two sides. Best score: the highest compare.similarity the generated task reaches against any reference task.

| # | Reference task not matched | Generated task not matched | Best score | Best reference task | Already matched? |
|---|---|---|---|---|---|
| 1 | Appraise property | Approved a loan application | 0.651 | Reject application | yes, to 'Rejected the application' (1.000) |
| 2 | Assess eligibility | Sent | 0.333 | Send acceptance pack | no |
| 3 | Send acceptance pack |  |  |  |  |

No unmatched generated task reaches the threshold against an unmatched reference task.

### Unmatched reference tasks: nearest generated task

| Reference task | Best score | Best generated task | Already matched? | Assigned below the threshold to |
|---|---|---|---|---|
| Appraise property | 0.439 | Prepared the acceptance pack | yes, to 'Prepare acceptance pack' (1.000) | Approved a loan application (0.333) |
| Assess eligibility | 0.556 | Assess the applicant’s | yes, to 'Assess loan risk' (0.706) | none |
| Send acceptance pack | 0.818 | Prepared the acceptance pack | yes, to 'Prepare acceptance pack' (1.000) | Sent (0.333) |

### Unmatched generated tasks: the assignment's partner

| Generated task | Assigned below the threshold to |
|---|---|
| Approved a loan application | Appraise property (0.333) |
| Sent | Send acceptance pack (0.333) |

### Matched pairs

| Reference task | Generated task | Score |
|---|---|---|
| Assess loan risk | Assess the applicant’s | 0.706 |
| Check credit history | Check history | 0.800 |
| Reject application | Rejected the application | 1.000 |
| Prepare acceptance pack | Prepared the acceptance pack | 1.000 |
