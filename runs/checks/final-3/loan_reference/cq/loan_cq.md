# Loan competency answers: the textbook reference (D12) beside the authored one

Run 2026-11-18T22:23:24+00:00 at revision-final-3-62-gdf78db4 (df78db4, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.5.0, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.dev0.

As text2bpmn/checks/cq_compare.py, for the loan case: each cell is both / reference / generated, with precision and recall; CQ2 and CQ6 count unordered pairs of alternative tasks; CQ8 gives reference / generated for tasks, decisions, parallel blocks and participants; n/a: CQ1 or CQ5 (about participants) against a reference that has none. Tasks are matched by text2bpmn.compare.match_tasks against the reference of the row. `authored` is reference_authored.bpmn (the reference of runs/checks/cq_compare), `textbook` is reference.bpmn.

## The references' own answers

| question | authored | textbook |
|---|---|---|
| cq1 Which tasks does each participant (lane / HumanResource) perform? | 7: (financial officer, check credit history); (loan officer, assess eligibility); (loan officer, notify application status); (loan officer, prepare acceptance pack); (loan officer, reject application); (property appraiser, appraise property); (system, assess loan risk) | 0 (empty: the model has a task and the graph holds what the query reads, but no row satisfies the question) |
| cq2 Which decisions does the process contain, and which task follows each outcome? | 1: {prepare acceptance pack, reject application} | 1: {prepare acceptance pack, reject application} |
| cq3 Which tasks can be executed in parallel? | 2: {appraise property, assess loan risk}; {appraise property, check credit history} | 2: {appraise property, assess loan risk}; {appraise property, check credit history} |
| cq4 What are the direct successors of a given task? | 7: (appraise property, ParallelGateway); (assess eligibility, ExclusiveGateway); (assess loan risk, ParallelGateway); (check credit history, Task, assess loan risk); (notify application status, EndEvent); (prepare acceptance pack, ExclusiveGateway); (reject application, ExclusiveGateway) | 7: (appraise property, ParallelGateway); (assess eligibility, ExclusiveGateway); (assess loan risk, ParallelGateway); (check credit history, Task, assess loan risk); (prepare acceptance pack, Task, send acceptance pack); (reject application, EndEvent); (send acceptance pack, EndEvent) |
| cq5 Where does work pass from one participant to another? | 3: (appraise property, assess eligibility); (assess loan risk, assess eligibility); (check credit history, assess loan risk) | 0 (empty: no such construct in the model (no pair of tasks in different lanes)) |
| cq6 Which tasks are executed only when a condition does not hold? | 1: {prepare acceptance pack, reject application} | 2: {prepare acceptance pack, reject application}; {reject application, send acceptance pack} |
| cq7 Which tasks are performed before the first decision? | 4: appraise property; assess eligibility; assess loan risk; check credit history | 4: appraise property; assess eligibility; assess loan risk; check credit history |
| cq8 How many tasks, decisions, parallel blocks and participants does the process have? | tasks 7, decisions 1, parallel_blocks 1, participants 4 | tasks 7, decisions 1, parallel_blocks 1, participants 0 |

## Generated against each reference

| configuration | reference | cq1 | cq2 | cq3 | cq4 | cq5 | cq6 | cq7 | cq8 |
|---|---|---|---|---|---|---|---|---|---|
| BERT, LLM | authored | 3/7/6 (P 0.50, R 0.43) | 1/1/1 (P 1.00, R 1.00) | 0/2/0 (P -, R 0.00) | 2/7/6 (P 0.33, R 0.29) | 1/3/2 (P 0.50, R 0.33) | 1/1/2 (P 0.50, R 1.00) | 2/4/3 (P 0.67, R 0.50) | task 7/6 deci 1/1 para 1/0 part 4/3 |
| BERT, LLM | textbook | n/a | 1/1/1 (P 1.00, R 1.00) | 0/2/0 (P -, R 0.00) | 1/7/6 (P 0.17, R 0.14) | n/a | 1/2/2 (P 0.50, R 0.50) | 2/4/3 (P 0.67, R 0.50) | task 7/6 deci 1/1 para 1/0 part 0/3 |
| BERT, no LLM | authored | 3/7/6 (P 0.50, R 0.43) | 0/1/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) | 1/7/6 (P 0.17, R 0.14) | 1/3/2 (P 0.50, R 0.33) | 0/1/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | task 7/6 deci 1/0 para 1/0 part 4/3 |
| BERT, no LLM | textbook | n/a | 0/1/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) | 1/7/6 (P 0.17, R 0.14) | n/a | 0/2/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | task 7/6 deci 1/0 para 1/0 part 0/3 |
| GLiNER, LLM | authored | 3/7/5 (P 0.60, R 0.43) | 1/1/1 (P 1.00, R 1.00) | 0/2/0 (P -, R 0.00) | 2/7/5 (P 0.40, R 0.29) | 0/3/1 (P 0.00, R 0.00) | 1/1/2 (P 0.50, R 1.00) | 1/4/2 (P 0.50, R 0.25) | task 7/5 deci 1/1 para 1/0 part 4/2 |
| GLiNER, LLM | textbook | n/a | 1/1/1 (P 1.00, R 1.00) | 0/2/0 (P -, R 0.00) | 1/7/5 (P 0.20, R 0.14) | n/a | 1/2/2 (P 0.50, R 0.50) | 1/4/2 (P 0.50, R 0.25) | task 7/5 deci 1/1 para 1/0 part 0/2 |
| GLiNER, no LLM | authored | 3/7/5 (P 0.60, R 0.43) | 0/1/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) | 0/7/5 (P 0.00, R 0.00) | 0/3/1 (P 0.00, R 0.00) | 0/1/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | task 7/5 deci 1/0 para 1/0 part 4/2 |
| GLiNER, no LLM | textbook | n/a | 0/1/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) | 0/7/5 (P 0.00, R 0.00) | n/a | 0/2/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) | task 7/5 deci 1/0 para 1/0 part 0/2 |

## What changes from the authored to the textbook reference

- BERT, LLM, cq1: 3/7/6 (P 0.50, R 0.43) -> n/a
- BERT, LLM, cq4: 2/7/6 (P 0.33, R 0.29) -> 1/7/6 (P 0.17, R 0.14)
- BERT, LLM, cq5: 1/3/2 (P 0.50, R 0.33) -> n/a
- BERT, LLM, cq6: 1/1/2 (P 0.50, R 1.00) -> 1/2/2 (P 0.50, R 0.50)
- BERT, LLM, cq8: task 7/6 deci 1/1 para 1/0 part 4/3 -> task 7/6 deci 1/1 para 1/0 part 0/3
- BERT, no LLM, cq1: 3/7/6 (P 0.50, R 0.43) -> n/a
- BERT, no LLM, cq5: 1/3/2 (P 0.50, R 0.33) -> n/a
- BERT, no LLM, cq6: 0/1/0 (P -, R 0.00) -> 0/2/0 (P -, R 0.00)
- BERT, no LLM, cq8: task 7/6 deci 1/0 para 1/0 part 4/3 -> task 7/6 deci 1/0 para 1/0 part 0/3
- GLiNER, LLM, cq1: 3/7/5 (P 0.60, R 0.43) -> n/a
- GLiNER, LLM, cq4: 2/7/5 (P 0.40, R 0.29) -> 1/7/5 (P 0.20, R 0.14)
- GLiNER, LLM, cq5: 0/3/1 (P 0.00, R 0.00) -> n/a
- GLiNER, LLM, cq6: 1/1/2 (P 0.50, R 1.00) -> 1/2/2 (P 0.50, R 0.50)
- GLiNER, LLM, cq8: task 7/5 deci 1/1 para 1/0 part 4/2 -> task 7/5 deci 1/1 para 1/0 part 0/2
- GLiNER, no LLM, cq1: 3/7/5 (P 0.60, R 0.43) -> n/a
- GLiNER, no LLM, cq5: 0/3/1 (P 0.00, R 0.00) -> n/a
- GLiNER, no LLM, cq6: 0/1/0 (P -, R 0.00) -> 0/2/0 (P -, R 0.00)
- GLiNER, no LLM, cq8: task 7/5 deci 1/0 para 1/0 part 4/2 -> task 7/5 deci 1/0 para 1/0 part 0/2
