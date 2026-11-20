# Table 6: The pairwise classifier on the 302 constructed pairs

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 6` (text2bpmn/paper_tables.py) from `benchmark_silver_2.jsonl`, `runs/final/table3_302/benchmark.md`, `runs/final/table3_302/log.txt`. Draft: s43.pdf (2026-11-13), Section 4.3.

| Label | Pairs | P | R | F1 | COND | TRUE | FALSE | SEQ | PAR |
|---|---|---|---|---|---|---|---|---|---|
| CONDITION DEF | 48 | 1.000 | 1.000 | 1.000 | 48 | 0 | 0 | 0 | 0 |
| TRUE BRANCH | 73 | 0.785 | 1.000 | 0.880 | 0 | 73 | 0 | 0 | 0 |
| FALSE BRANCH | 69 | 1.000 | 0.710 | 0.831 | 0 | 20 | 49 | 0 | 0 |
| SEQUENCE | 66 | 1.000 | 0.939 | 0.969 | 0 | 0 | 0 | 62 | 4 |
| PARALLEL | 46 | 0.920 | 1.000 | 0.958 | 0 | 0 | 0 | 0 | 46 |

With it, in the section's text:

| value | rebuilt | draft |
|---|---|---|
| accuracy | 0.921 (278/302) | 0.921 (278/302) |
| macro F1 | 0.927 | 0.927 |
| weighted F1 | 0.919 | 0.919 |
| FALSE BRANCH labelled TRUE BRANCH, of them without an else-marker | 20, 20 of 23 | 20, 20 of 23 |
| SEQUENCE labelled PARALLEL | 4 | 4 |
| correct under the syntactic scheme | 295 of 302 (97.7%) | 295 of 302 (97.7%) |

## Against the draft

All 51 values compared (cells and text values) are the draft's.

## Checks

- the report's predictions equal the log's answers, pair for pair: True
