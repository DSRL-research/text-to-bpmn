# Table 2: Entity distribution (PET v1.1)

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 2` (text2bpmn/paper_tables.py) from `pet_data/PETv1.1-relations.json`. Draft: bpmn_springer_format_2_reviewing_1.pdf (2026-11-12; its .docx, 2026-11-12, has the same tables).

| Entity type | Count | % |
|---|---|---|
| Activity | 502 | 29.9 |
| Activity Data | 459 | 27.3 |
| Actor | 449 | 26.7 |
| XOR Gateway | 117 | 7.0 |
| Condition Specification | 80 | 4.8 |
| Further Specification | 64 | 3.8 |
| AND Gateway | 8 | 0.5 |
| Total | 1679 | 100.0 |

With it, in the section's text:

| value | rebuilt | draft |
|---|---|---|
| sentences | 417 | 417 |
| relations | 1832 | 1832 |
| Flow relations | 675 | 675 |

## Against the draft

All 19 values compared (cells and text values) are the draft's.

## Checks

- every mention is of one of the seven types: True
