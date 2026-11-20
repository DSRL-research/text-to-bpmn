# Table 10: The reference processes

Run 2026-11-20T09:01:18+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Rebuilt by `python3 -m text2bpmn.paper_tables 10` (text2bpmn/paper_tables.py) from `runs/final-3/cases`, `runs/final-3/cases_no_llm`, `runs/gliner-3/cases_gliner`, `runs/gliner-3/cases_gliner_no_llm`, `text2bpmn/cases/loan/reference.bpmn`, `text2bpmn/cases/goods_dispatch/reference.bpmn`, `text2bpmn/cases/healthcare/reference.bpmn`, `text2bpmn/cases/loan/reference_authored.bpmn`. Draft: s46-2.pdf (2026-11-18), Section 4.6, version 3: the loan rows against the textbook reference (D12).

| Process, configuration | Tasks | Gateways | Flows | GED | |G| gen./ref. | RGED | Sim | Footprint |
|---|---|---|---|---|---|---|---|---|
| Loan, BERT, method | .615 (4/2/3) | .400 (1/1/2) | .182 (1/4/5) | 23.49 | 20 / 26 | 0.511 | 0.489 | 0.059 |
| Loan, BERT, no LLM | .615 | .000 (0/0/3) | .182 (1/4/5) | 24.49 | 15 / 26 | 0.597 | 0.403 | 0.059 |
| Loan, GLiNER, method | .500 (3/2/4) | .400 (1/1/2) | .400 (2/2/4) | 21.25 | 18 / 26 | 0.483 | 0.517 | 0.133 |
| Loan, GLiNER, no LLM | .500 | .000 | .200 (1/3/5) | 27.25 | 13 / 26 | 0.699 | 0.301 | 0.062 |
| Goods dispatch, BERT, method | .588 (5/5/2) | .667 (4/2/2) | .200 (2/10/6) | 40.91 | 38 / 32 | 0.584 | 0.416 | 0.070 |
| Goods dispatch, BERT, no LLM | .588 | .000 (0/0/6) | .118 (1/8/7) | 37.91 | 23 / 32 | 0.689 | 0.311 | 0.025 |
| Goods dispatch, GLiNER, method | .750 (6/3/1) | .500 (3/3/3) | .118 (1/8/7) | 39.52 | 36 / 32 | 0.581 | 0.419 | 0.024 |
| Goods dispatch, GLiNER, no LLM | .750 | .000 | .125 (1/7/7) | 33.52 | 21 / 32 | 0.632 | 0.368 | 0.026 |
| Healthcare, BERT, method | .618 (17/15/6) | .667 (6/0/6) | .032 (1/34/27) | 114.12 | 82 / 85 | 0.683 | 0.317 | 0.013 |
| Healthcare, BERT, no LLM | .618 | .000 (0/0/12) | .034 (1/30/27) | 108.12 | 67 / 85 | 0.711 | 0.289 | 0.014 |
| Healthcare, GLiNER, method | .627 (16/12/7) | .667 (6/0/6) | .172 (5/25/23) | 94.53 | 75 / 85 | 0.591 | 0.409 | 0.074 |
| Healthcare, GLiNER, no LLM | .627 | .000 | .182 (5/22/23) | 95.53 | 59 / 85 | 0.663 | 0.337 | 0.078 |

With it, in the section's text:

| value | rebuilt | draft |
|---|---|---|
| task F1 with BERT, lowest and highest | 59% and 62% | 59% and 62% |
| gateways of the three references found with BERT and the LLM, of all; wrong | 11 of 21; 3 | 11 of 21; 3 |
| flows matching the references, BERT, with / without the LLM | 4 / 3 | 4 / 3 |
| GED with / without the LLM, BERT: loan; goods dispatch; healthcare | 23.49 / 24.49; 40.91 / 37.91; 114.12 / 108.12 | 23.49 / 24.49; 40.91 / 37.91; 114.12 / 108.12 |
| flows the references do not have, BERT, with / without the LLM: goods dispatch; healthcare | 10 / 8; 34 / 30 | 10 / 8; 34 / 30 |
| GED over the larger graph, BERT, with the LLM against without: loan, goods dispatch, healthcare | lower, lower, higher | lower, lower, higher |
| footprint similarity, lowest to highest | 0.01 to 0.13 | 0.01 to 0.13 |
| GLiNER against BERT, with the LLM | tasks better on goods dispatch, healthcare, worse on loan; flows better on loan, healthcare; GED lower on loan, goods dispatch, healthcare; more gateways found with BERT on goods dispatch | tasks better on goods dispatch, healthcare, worse on loan; flows better on loan, healthcare; GED lower on loan, goods dispatch, healthcare; more gateways found with BERT on goods dispatch |

## Against the draft

All 104 values compared (cells and text values) are the draft's.

## Checks

- loan: text2bpmn/cases/loan/reference_authored.bpmn, the reference the runs scored against, is the one at revision-final-3: True
- loan, BERT, method: scored again from the XML = the run's comparison.json: True
- loan, BERT, method: against reference_authored.bpmn, scored again = the run's own score, comparison_authored.json: True
- loan, BERT, method: RGED = the saved rged_combined: True
- loan, BERT, no LLM: scored again from the XML = the run's comparison.json: True
- loan, BERT, no LLM: against reference_authored.bpmn, scored again = the run's own score, comparison_authored.json: True
- loan, BERT, no LLM: RGED = the saved rged_combined: True
- loan, GLiNER, method: scored again from the XML = the run's comparison.json: True
- loan, GLiNER, method: against reference_authored.bpmn, scored again = the run's own score, comparison_authored.json: True
- loan, GLiNER, method: RGED = the saved rged_combined: True
- loan, GLiNER, no LLM: scored again from the XML = the run's comparison.json: True
- loan, GLiNER, no LLM: against reference_authored.bpmn, scored again = the run's own score, comparison_authored.json: True
- loan, GLiNER, no LLM: RGED = the saved rged_combined: True
- goods_dispatch: text2bpmn/cases/goods_dispatch/reference.bpmn is the reference at revision-final-3: True
- goods_dispatch, BERT, method: scored again from the XML = the run's comparison.json: True
- goods_dispatch, BERT, method: RGED = the saved rged_combined: True
- goods_dispatch, BERT, no LLM: scored again from the XML = the run's comparison.json: True
- goods_dispatch, BERT, no LLM: RGED = the saved rged_combined: True
- goods_dispatch, GLiNER, method: scored again from the XML = the run's comparison.json: True
- goods_dispatch, GLiNER, method: RGED = the saved rged_combined: True
- goods_dispatch, GLiNER, no LLM: scored again from the XML = the run's comparison.json: True
- goods_dispatch, GLiNER, no LLM: RGED = the saved rged_combined: True
- healthcare: text2bpmn/cases/healthcare/reference.bpmn is the reference at revision-final-3 (with its documented score-neutral corrections): True
- healthcare, BERT, method: scored again from the XML = the run's comparison.json: True
- healthcare, BERT, method: RGED = the saved rged_combined: True
- healthcare, BERT, no LLM: scored again from the XML = the run's comparison.json: True
- healthcare, BERT, no LLM: RGED = the saved rged_combined: True
- healthcare, GLiNER, method: scored again from the XML = the run's comparison.json: True
- healthcare, GLiNER, method: RGED = the saved rged_combined: True
- healthcare, GLiNER, no LLM: scored again from the XML = the run's comparison.json: True
- healthcare, GLiNER, no LLM: RGED = the saved rged_combined: True
- tasks are the same with and without the LLM, for each recogniser and case: True
