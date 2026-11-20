# Table 5: Flow relations on PET under the strict protocol, with gold entities

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 5` (text2bpmn/paper_tables.py) from `text2bpmn/baselines/neuberger (pet_strict --fetch)`, `runs/final-3/pet_decisions`, `runs/final-3/pet_no_llm`. Draft: s43.pdf (2026-11-13), Section 4.3.

| System | P | R | F1 (folds) | F1 (pooled) |
|---|---|---|---|---|
| RuleRelEx [23] | 0.737 | 0.796 | 0.765 | 0.762 |
| BoostRelEx [23] | 0.881 | 0.697 | 0.777 | 0.775 |
| GPT-4o [Springer], none | 0.795 | 0.723 | 0.757 | 0.755 |
| GPT-4o [Springer], three documents | 0.854 | 0.800 | 0.826 | 0.825 |
| GPT-4-turbo [Springer], three documents | 0.862 | 0.815 | 0.838 | 0.836 |
| Llama 3 70B [Springer], three documents | 0.849 | 0.788 | 0.817 | 0.814 |
| Claude 3 Opus [Springer], three documents | 0.893 | 0.859 | 0.875 | 0.871 |
| Textual order (no LLM) | 0.797 | 0.757 | 0.777 | 0.776 |
| This method | 0.804 | 0.807 | 0.805 | 0.805 |

With it, in the section's text:

| value | rebuilt | draft |
|---|---|---|
| method - RuleRelEx | +0.043 [+0.016, +0.073] | +0.043 [+0.016, +0.073] |
| method - textual order | +0.028 [+0.008, +0.054] | +0.028 [+0.008, +0.054] |
| method - GPT-4o, none | +0.049 [-0.001, +0.104] | +0.049 [-0.001, +0.104] |
| method - GPT-4o, three | -0.020 [-0.064, +0.020] | -0.020 [-0.064, +0.020] |
| method - Claude 3 Opus, three | -0.066 [-0.110, -0.026] | -0.066 [-0.110, -0.026] |
| method, rule 1 alone (pooled) | 0.610 | 0.610 |
| gold mentions (PET v1.1), of them exactly Neuberger et al.'s | 1,679, 1,654 | 1,679, 1,654 |
| the others: actors, activity data, activities | 12, 12, 1 | 12, 12, 1 |
| of the others, in a Flow relation (PET v1.1 or theirs) | 0 | 0 |

## Against the draft

All 45 values compared (cells and text values) are the draft's.

## Checks

- gold Flow relations: 674
