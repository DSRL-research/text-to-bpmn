# Competency answers: generated against reference, as sets

Run 2026-11-20T06:08:52+00:00 at revision-final-3-76-g99107f3 (99107f3, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Command: `python3 -m text2bpmn.checks.cq_compare runs/final-3/cases runs/final-3/cases_no_llm runs/gliner-3/cases_gliner runs/gliner-3/cases_gliner_no_llm --layout release --out runs/checks/final-3/cq_compare --references runs/checks/final-3/cq_compare/references`

Each cell: both / reference / generated, with precision and recall; CQ2 and CQ6 count unordered pairs of alternative tasks; CQ8 gives reference / generated for tasks, decisions, parallel blocks and participants; n/a: a question about participants (CQ1, CQ5) on a reference that has none. Tasks are matched by text2bpmn.compare.match_tasks (compare.similarity, threshold 0.5, one-to-one). References: `text2bpmn/cases/loan/reference.bpmn`, `text2bpmn/cases/goods_dispatch/reference.bpmn`, `text2bpmn/cases/healthcare/reference.bpmn`.

## loan

| source | cq1 | cq2 | cq3 | cq4 | cq5 | cq6 | cq7 | cq8 |
|---|---|---|---|---|---|---|---|---|
| runs/final-3/cases | n/a | 1/1/1 (P 1.00, R 1.00) | 0/2/0 (P -, R 0.00) | 1/7/6 (P 0.17, R 0.14) | n/a | 1/2/2 (P 0.50, R 0.50) | 2/4/3 (P 0.67, R 0.50) | task 7/6 deci 1/1 para 1/0 part 0/3 |
| runs/final-3/cases_no_llm | n/a | 0/1/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) | 1/7/6 (P 0.17, R 0.14) | n/a | 0/2/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | task 7/6 deci 1/0 para 1/0 part 0/3 |
| runs/gliner-3/cases_gliner | n/a | 1/1/1 (P 1.00, R 1.00) | 0/2/0 (P -, R 0.00) | 1/7/5 (P 0.20, R 0.14) | n/a | 1/2/2 (P 0.50, R 0.50) | 1/4/2 (P 0.50, R 0.25) | task 7/5 deci 1/1 para 1/0 part 0/2 |
| runs/gliner-3/cases_gliner_no_llm | n/a | 0/1/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) | 0/7/5 (P 0.00, R 0.00) | n/a | 0/2/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | task 7/5 deci 1/0 para 1/0 part 0/2 |

## goods_dispatch

| source | cq1 | cq2 | cq3 | cq4 | cq5 | cq6 | cq7 | cq8 |
|---|---|---|---|---|---|---|---|---|
| runs/final-3/cases | 2/7/10 (P 0.20, R 0.29) | 0/2/1 (P 0.00, R 0.00) | 0/5/1 (P 0.00, R 0.00) | 1/5/10 (P 0.10, R 0.20) | 2/4/9 (P 0.22, R 0.50) | 0/4/3 (P 0.00, R 0.00) | 1/1/2 (P 0.50, R 1.00) | task 7/10 deci 1/2 para 1/1 part 3/5 |
| runs/final-3/cases_no_llm | 2/7/10 (P 0.20, R 0.29) | 0/2/0 (P -, R 0.00) | 0/5/0 (P -, R 0.00) | 0/5/10 (P 0.00, R 0.00) | 1/4/6 (P 0.17, R 0.25) | 0/4/0 (P -, R 0.00) | 0/1/0 (P -, R 0.00) | task 7/10 deci 1/0 para 1/0 part 3/5 |
| runs/gliner-3/cases_gliner | 3/7/9 (P 0.33, R 0.43) | 0/2/3 (P 0.00, R 0.00) | 0/5/0 (P -, R 0.00) | 2/5/9 (P 0.22, R 0.40) | 1/4/5 (P 0.20, R 0.25) | 0/4/2 (P 0.00, R 0.00) | 0/1/0 (P -, R 0.00) | task 7/9 deci 1/3 para 1/0 part 3/4 |
| runs/gliner-3/cases_gliner_no_llm | 3/7/9 (P 0.33, R 0.43) | 0/2/0 (P -, R 0.00) | 0/5/0 (P -, R 0.00) | 0/5/9 (P 0.00, R 0.00) | 1/4/4 (P 0.25, R 0.25) | 0/4/0 (P -, R 0.00) | 0/1/0 (P -, R 0.00) | task 7/9 deci 1/0 para 1/0 part 3/4 |

## healthcare

| source | cq1 | cq2 | cq3 | cq4 | cq5 | cq6 | cq7 | cq8 |
|---|---|---|---|---|---|---|---|---|
| runs/final-3/cases | 8/23/32 (P 0.25, R 0.35) | 0/17/3 (P 0.00, R 0.00) | 0/4/0 (P -, R 0.00) | 2/23/32 (P 0.06, R 0.09) | 1/14/16 (P 0.06, R 0.07) | 0/16/0 (P -, R 0.00) | 0/0/1 (P 0.00, R -) | task 23/32 deci 7/3 para 1/0 part 6/8 |
| runs/final-3/cases_no_llm | 8/23/32 (P 0.25, R 0.35) | 0/17/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | 1/23/32 (P 0.03, R 0.04) | 1/14/16 (P 0.06, R 0.07) | 0/16/0 (P -, R 0.00) | 0/0/0 (P -, R -) | task 23/32 deci 7/0 para 1/0 part 6/8 |
| runs/gliner-3/cases_gliner | 8/23/28 (P 0.29, R 0.35) | 0/17/5 (P 0.00, R 0.00) | 0/4/0 (P -, R 0.00) | 7/23/28 (P 0.25, R 0.30) | 1/14/15 (P 0.07, R 0.07) | 0/16/3 (P 0.00, R 0.00) | 0/0/0 (P -, R -) | task 23/28 deci 7/3 para 1/0 part 6/7 |
| runs/gliner-3/cases_gliner_no_llm | 8/23/28 (P 0.29, R 0.35) | 0/17/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | 5/23/28 (P 0.18, R 0.22) | 1/14/12 (P 0.08, R 0.07) | 0/16/0 (P -, R 0.00) | 0/0/0 (P -, R -) | task 23/28 deci 7/0 para 1/0 part 6/7 |
