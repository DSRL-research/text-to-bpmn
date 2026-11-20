# Table 9: Branch heads of PET's 75 decisions

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 9` (text2bpmn/paper_tables.py) from `runs/final-3/pet_no_llm`, `runs/final-3/pet_no_and`, `runs/final-3/pet_decisions`, `text2bpmn/baselines/neuberger (pet_strict --fetch)`. Draft: s45-2.pdf (2026-11-17; s45-3.pdf is the same file), Section 4.5.

| Relation stage | Right | Not built | Wrong head | Extra head | Missed | Share right |
|---|---|---|---|---|---|---|
| Textual order (no LLM) | 32 | 38 | 2 | 0 | 3 | 0.427 |
| Method without the LLM | 24 | 46 | 1 | 0 | 4 | 0.320 |
| This method | 37 | 17 | 15 | 6 | 0 | 0.493 |

With it, in the section's text:

| value | rebuilt | draft |
|---|---|---|
| decisions; with two, three or more, one branch head | 75; 57, 11, 7 | 75; 57, 11, 7 |
| method - method without the LLM | +0.173 [+0.070, +0.293] | +0.173 [+0.070, +0.293] |
| method - textual order | +0.067 [-0.026, +0.169] | +0.067 [-0.026, +0.169] |

## Against the draft

All 21 values compared (cells and text values) are the draft's.

## Checks

- decisions with no branch head in PET: 0
