# Table 3: Strict F1 per mention type on the 42 test sentences

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 3` (text2bpmn/paper_tables.py) from `text2bpmn/baselines/comparison_spec_315.json`, `text2bpmn/baselines/test_bert_315_dev60.json`, `text2bpmn/baselines/TEST_ft_A-small-v2.1-315.json`, `pet_test.json`. Draft: bpmn_springer_format_2_reviewing_1.pdf (2026-11-12; its .docx, 2026-11-12, has the same tables).

| Mention type | Support | BERT | GLiNER small v2.1 |
|---|---|---|---|
| Activity | 62 | 0.672 | 0.872 |
| Activity Data | 59 | 0.711 | 0.775 |
| Actor | 49 | 0.874 | 0.960 |
| Condition Specification | 10 | 0.706 | 0.750 |
| Further Specification | 6 | 0.000 | 0.000 |
| XOR Gateway | 11 | 0.900 | 0.900 |
| AND Gateway | 0 | - | - |

## Against the draft

All 21 values compared (cells and text values) are the draft's.
