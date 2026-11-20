# Table 7: Lane assignment on PET

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 7` (text2bpmn/paper_tables.py) from `runs/final-3/coref_ablation`, `runs/gliner-3/lanes_gliner`, `pet_data/PETv1.1-relations.json`. Draft: s44.pdf (2026-11-13), Section 4.4.

|  | BERT, with FastCoref | BERT, without | GLiNER, with FastCoref |
|---|---|---|---|
| Of the recognised activities | 83.3% (315/378) | 76.9% (293/381) | 82.5% (306/371) |
| Of all 396 gold activities | 79.5% | 74.0% | 77.3% |
| With a pronoun as performer | 40.0% (22/55) | 0.0% (0/56) | 41.1% (23/56) |
| Without the 122 with a recipient | 82.6% (214/259) | 77.9% (204/262) | 81.7% (205/251) |
| Tasks in Main Process | 5.1% | 5.0% | 4.2% |

With it, in the section's text:

| value | rebuilt | draft |
|---|---|---|
| gold activities with a performer, documents | 396, 43 | 396, 43 |
| of them with an actor recipient | 122 | 122 |
| with - without FastCoref, of recognised | +0.064 [+0.023, +0.114] | +0.064 [+0.023, +0.114] |
| with - without FastCoref, of all gold | +0.056 [+0.017, +0.104] | +0.056 [+0.017, +0.104] |
| GLiNER - BERT, of recognised | -0.009 [-0.050, +0.026] | -0.009 [-0.050, +0.026] |
| GLiNER - BERT, of all gold | -0.023 [-0.068, +0.015] | -0.023 [-0.068, +0.015] |

## Against the draft

19 of 21 values compared are the draft's; these differ:

- Tasks in Main Process, BERT, without: draft 5.1%, rebuilt 5.0%. 26 of 515 tasks = 5.05%, 5.0% to one place; lane_scores.json stores the share rounded to four places (0.0505), which prints as 5.1%
- Tasks in Main Process, GLiNER, with FastCoref: draft 4.3%, rebuilt 4.2%. 22 of 518 tasks = 4.25%, 4.2% to one place; lane_scores.json stores 0.0425, which the draft rounded up to 4.3%

## Checks

- BERT, with FastCoref: the rows equal the run's lane_scores.json: True
- BERT, without: the rows equal the run's lane_scores.json: True
- GLiNER, with FastCoref: the rows equal the run's lane_scores.json: True
- Main Process tasks, of all tasks: {'BERT, with FastCoref': '26/514', 'BERT, without': '26/515', 'GLiNER, with FastCoref': '22/518'}
