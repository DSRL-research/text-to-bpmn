# Competency questions: queries, answers, scores and run times

Run 2026-11-20T06:08:52+00:00 at revision-final-3-76-g99107f3 (99107f3, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Command: `python3 -m text2bpmn.checks.cq_compare runs/final-3/cases runs/final-3/cases_no_llm runs/gliner-3/cases_gliner runs/gliner-3/cases_gliner_no_llm --layout release --out runs/checks/final-3/cq_compare --references runs/checks/final-3/cq_compare/references`. Scores and keys as in `cq_compare.md`: a generated task is named by the reference task it matches, or `(unmatched) <label>`; CQ2 and CQ6 are unordered pairs of alternative tasks (CQ6 from the alternatives query below); CQ8 gives the four counts.

## The queries (text2bpmn/checks/cq/, verbatim)

### cq1

```sparql
# CQ1 Which tasks does each participant (lane / HumanResource) perform?
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?participant ?task WHERE {
  ?t a b:Task ; rdfs:label ?task ; b:has_resource ?r .
  ?r a b:HumanResource ; rdfs:label ?participant .
} ORDER BY ?participant ?task
```

### cq2

```sparql
# CQ2 Which decisions does the process contain, and which task follows each outcome?
# A decision is an exclusive gateway with two or more outgoing flows. The task
# that follows an outcome is the first task on that flow's path.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?decision ?gateway ?flow_id ?outcome ?relation ?next_task WHERE {
  { SELECT ?g WHERE { ?g a b:ExclusiveGateway . ?f b:has_sourceRef ?g } GROUP BY ?g HAVING (COUNT(?f) >= 2) }
  OPTIONAL { ?g rdfs:label ?decision }
  BIND(STRAFTER(STR(?g), "#") AS ?gateway)
  ?flow b:has_sourceRef ?g ; b:has_targetRef ?target .
  BIND(STRAFTER(STR(?flow), "#") AS ?flow_id)
  OPTIONAL { ?flow t:branch_condition ?outcome }
  OPTIONAL { ?flow t:extracted_relation ?relation }
  { ?target a b:Task . BIND(?target AS ?n) }
  UNION
  { FILTER NOT EXISTS { ?target a b:Task }
    ?target b:has_nextFlowNode+ ?n . ?n a b:Task .
    FILTER NOT EXISTS { ?target b:has_nextFlowNode+ ?m . ?m b:has_nextFlowNode+ ?n . ?m a b:Task } }
  ?n rdfs:label ?next_task .
} ORDER BY ?gateway ?outcome ?next_task
```

### cq3

```sparql
# CQ3 Which tasks can be executed in parallel?
# Two tasks on different branches of one parallel split, before the branches meet:
# each task is reached from its own branch and not from the other one, so a task at
# or after the block's join (reached from both branches) is not counted, whatever the
# join's type. Neither task is reachable from the other.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?split ?task_a ?task_b WHERE {
  ?p a b:ParallelGateway .
  ?f1 b:has_sourceRef ?p ; b:has_targetRef ?x1 .
  ?f2 b:has_sourceRef ?p ; b:has_targetRef ?x2 .
  FILTER(?x1 != ?x2)
  ?x1 b:has_nextFlowNode* ?a . ?a a b:Task ; rdfs:label ?task_a .
  ?x2 b:has_nextFlowNode* ?c . ?c a b:Task ; rdfs:label ?task_b .
  FILTER(STR(?a) < STR(?c))
  FILTER NOT EXISTS { ?x2 b:has_nextFlowNode* ?a }
  FILTER NOT EXISTS { ?x1 b:has_nextFlowNode* ?c }
  FILTER NOT EXISTS { ?a b:has_nextFlowNode+ ?c }
  FILTER NOT EXISTS { ?c b:has_nextFlowNode+ ?a }
  BIND(STRAFTER(STR(?p), "#") AS ?split)
} ORDER BY ?split ?task_a ?task_b
```

### cq4

```sparql
# CQ4 What are the direct successors of a given task?
# Answered for every task; bind ?t (e.g. VALUES ?t { b:Activity_... }) for one.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?task ?successor ?successor_type WHERE {
  ?t a b:Task ; rdfs:label ?task ; b:has_nextFlowNode ?s .
  ?s a ?type .
  FILTER(?type IN (b:Task, b:ExclusiveGateway, b:ParallelGateway, b:StartEvent, b:EndEvent))
  OPTIONAL { ?s rdfs:label ?successor }
  BIND(STRAFTER(STR(?type), "#") AS ?successor_type)
} ORDER BY ?task ?successor
```

### cq5

```sparql
# CQ5 Where does work pass from one participant to another?
# A task followed, directly or through gateways, by the next task in another lane.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?from_lane ?from_task ?to_lane ?to_task WHERE {
  ?a a b:Task ; rdfs:label ?from_task ; b:has_resource ?ra .
  ?c a b:Task ; rdfs:label ?to_task ; b:has_resource ?rc .
  FILTER(?ra != ?rc)
  ?a b:has_nextFlowNode+ ?c .
  FILTER NOT EXISTS { ?a b:has_nextFlowNode+ ?m . ?m b:has_nextFlowNode+ ?c . ?m a b:Task }
  ?ra rdfs:label ?from_lane . ?rc rdfs:label ?to_lane .
} ORDER BY ?from_lane ?from_task
```

### cq6

```sparql
# CQ6 Which tasks are executed only when a condition does not hold?
# Tasks reachable from a decision's false outcome and from none of its other outcomes.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?decision ?task WHERE {
  ?no b:has_sourceRef ?g ; b:has_targetRef ?x .
  { ?no t:extracted_relation ?rel . FILTER(STR(?rel) = "FALSE_BRANCH") }
  UNION { ?no t:branch_condition ?cond . FILTER(STR(?cond) = "No") }
  ?x b:has_nextFlowNode* ?task_node . ?task_node a b:Task ; rdfs:label ?task .
  FILTER NOT EXISTS {
    ?other b:has_sourceRef ?g ; b:has_targetRef ?y . FILTER(?other != ?no)
    ?y b:has_nextFlowNode* ?task_node }
  OPTIONAL { ?g rdfs:label ?decision }
} ORDER BY ?decision ?task
```

### cq7

```sparql
# CQ7 Which tasks are performed before the first decision?
# Tasks that lead to a decision and follow none.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?task WHERE {
  { SELECT ?g WHERE { ?g a b:ExclusiveGateway . ?f b:has_sourceRef ?g } GROUP BY ?g HAVING (COUNT(?f) >= 2) }
  ?t a b:Task ; rdfs:label ?task ; b:has_nextFlowNode+ ?g .
  FILTER NOT EXISTS {
    ?d a b:ExclusiveGateway . ?d b:has_nextFlowNode+ ?t .
    { SELECT ?d WHERE { ?d a b:ExclusiveGateway . ?e b:has_sourceRef ?d } GROUP BY ?d HAVING (COUNT(?e) >= 2) } }
} ORDER BY ?task
```

### cq8

```sparql
# CQ8 How many tasks, decisions, parallel blocks and participants does the process have?
# A parallel block is counted by its split: a parallel gateway with two or more outgoing flows.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT
  (COUNT(DISTINCT ?t) AS ?tasks) (COUNT(DISTINCT ?d) AS ?decisions)
  (COUNT(DISTINCT ?p) AS ?parallel_blocks) (COUNT(DISTINCT ?r) AS ?participants)
WHERE {
  { ?t a b:Task }
  UNION { SELECT ?d WHERE { ?d a b:ExclusiveGateway . ?f b:has_sourceRef ?d } GROUP BY ?d HAVING (COUNT(?f) >= 2) }
  UNION { SELECT ?p WHERE { ?p a b:ParallelGateway . ?f b:has_sourceRef ?p } GROUP BY ?p HAVING (COUNT(?f) >= 2) }
  UNION { ?r a b:HumanResource }
}
```

### alternatives (scores CQ6; text2bpmn/checks/cq_compare.py ALTERNATIVES)

```sparql
# For scoring CQ6 without polarity: for each decision, the tasks each outgoing
# flow reaches and no other outgoing flow of that decision does.
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?gateway ?flow_id ?task WHERE {
  { SELECT ?g WHERE { ?g a b:ExclusiveGateway . ?f b:has_sourceRef ?g } GROUP BY ?g HAVING (COUNT(?f) >= 2) }
  ?flow b:has_sourceRef ?g ; b:has_targetRef ?x .
  ?x b:has_nextFlowNode* ?node . ?node a b:Task ; rdfs:label ?task .
  FILTER NOT EXISTS {
    ?other b:has_sourceRef ?g ; b:has_targetRef ?y . FILTER(?other != ?flow)
    ?y b:has_nextFlowNode* ?node }
  BIND(STRAFTER(STR(?g), "#") AS ?gateway)
  BIND(STRAFTER(STR(?flow), "#") AS ?flow_id)
} ORDER BY ?gateway ?flow_id ?task
```

## Query run times (seconds; rdflib 7.6.0, 13th Gen Intel(R) Core(TM) i7-1355U)

| case | graph | cq1 | cq2 | cq3 | cq4 | cq5 | cq6 | cq7 | cq8 | total |
|---|---|---|---|---|---|---|---|---|---|---|
| loan | reference | 0.115 | 0.074 | 0.694 | 0.022 | 0.016 | 0.034 | 0.026 | 0.026 | 1.007 |
| loan | runs/final-3/cases | 0.007 | 0.056 | 0.044 | 0.033 | 0.031 | 0.026 | 0.033 | 0.025 | 0.255 |
| loan | runs/final-3/cases_no_llm | 0.011 | 0.063 | 0.025 | 0.021 | 0.036 | 0.037 | 0.022 | 0.025 | 0.240 |
| loan | runs/gliner-3/cases_gliner | 0.006 | 0.062 | 0.026 | 0.018 | 0.020 | 0.031 | 0.026 | 0.026 | 0.215 |
| loan | runs/gliner-3/cases_gliner_no_llm | 0.014 | 0.055 | 0.028 | 0.025 | 0.025 | 0.027 | 0.026 | 0.034 | 0.234 |
| goods_dispatch | reference | 0.010 | 0.121 | 0.511 | 0.024 | 0.030 | 0.030 | 0.027 | 0.031 | 0.784 |
| goods_dispatch | runs/final-3/cases | 0.009 | 0.151 | 1.661 | 0.032 | 0.098 | 0.038 | 0.045 | 0.035 | 2.069 |
| goods_dispatch | runs/final-3/cases_no_llm | 0.009 | 0.097 | 0.029 | 0.026 | 0.070 | 0.026 | 0.031 | 0.029 | 0.317 |
| goods_dispatch | runs/gliner-3/cases_gliner | 0.011 | 0.145 | 0.032 | 0.026 | 0.087 | 0.093 | 0.075 | 0.057 | 0.526 |
| goods_dispatch | runs/gliner-3/cases_gliner_no_llm | 0.015 | 0.115 | 0.041 | 0.025 | 0.056 | 0.031 | 0.026 | 0.029 | 0.338 |
| healthcare | reference | 0.014 | 2.490 | 43.721 | 0.026 | 0.832 | 0.062 | 0.149 | 0.025 | 47.319 |
| healthcare | runs/final-3/cases | 0.071 | 3.663 | 0.031 | 0.027 | 2.650 | 0.209 | 0.057 | 0.022 | 6.730 |
| healthcare | runs/final-3/cases_no_llm | 0.010 | 2.578 | 0.031 | 0.027 | 2.522 | 0.033 | 0.023 | 0.027 | 5.251 |
| healthcare | runs/gliner-3/cases_gliner | 0.011 | 2.248 | 0.041 | 0.035 | 1.623 | 0.141 | 0.067 | 0.025 | 4.191 |
| healthcare | runs/gliner-3/cases_gliner_no_llm | 0.010 | 1.465 | 0.028 | 0.024 | 1.457 | 0.028 | 0.019 | 0.027 | 3.058 |

| question | graphs | min | median | max |
|---|---|---|---|---|
| cq1 | 15 | 0.006 | 0.011 | 0.115 |
| cq2 | 15 | 0.055 | 0.121 | 3.663 |
| cq3 | 15 | 0.025 | 0.032 | 43.721 |
| cq4 | 15 | 0.018 | 0.026 | 0.035 |
| cq5 | 15 | 0.016 | 0.070 | 2.650 |
| cq6 | 15 | 0.026 | 0.033 | 0.209 |
| cq7 | 15 | 0.019 | 0.027 | 0.149 |
| cq8 | 15 | 0.022 | 0.027 | 0.057 |

## loan

Reference: `text2bpmn/cases/loan/reference.bpmn`.

### cq1 Which tasks does each participant (lane / HumanResource) perform?

- reference (0): none (the model has a task and the graph holds what the query reads, but no row satisfies the question)
- runs/final-3/cases: **n/a**; answer (6): (financial officer, check credit history); (loan officer, (unmatched) sent); (loan officer, assess loan risk); (loan officer, prepare acceptance pack); (loan officer, reject application); (property appraiser, (unmatched) approved loan application)
- runs/final-3/cases_no_llm: **n/a**; answer (6): (financial officer, check credit history); (loan officer, (unmatched) sent); (loan officer, assess loan risk); (loan officer, prepare acceptance pack); (loan officer, reject application); (property appraiser, (unmatched) approved loan application)
- runs/gliner-3/cases_gliner: **n/a**; answer (5): (loan officer, (unmatched) sent); (loan officer, assess eligibility); (loan officer, prepare acceptance pack); (loan officer, reject application); (property appraiser, (unmatched) approved loan application)
- runs/gliner-3/cases_gliner_no_llm: **n/a**; answer (5): (loan officer, (unmatched) sent); (loan officer, assess eligibility); (loan officer, prepare acceptance pack); (loan officer, reject application); (property appraiser, (unmatched) approved loan application)

### cq2 Which decisions does the process contain, and which task follows each outcome?

- reference (1): {prepare acceptance pack, reject application}
- runs/final-3/cases: **1/1/1 (P 1.00, R 1.00)**; answer (1): {prepare acceptance pack, reject application}
- runs/final-3/cases_no_llm: **0/1/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **1/1/1 (P 1.00, R 1.00)**; answer (1): {prepare acceptance pack, reject application}
- runs/gliner-3/cases_gliner_no_llm: **0/1/0 (P -, R 0.00)**; answer (0): none

### cq3 Which tasks can be executed in parallel?

- reference (2): {appraise property, assess loan risk}; {appraise property, check credit history}
- runs/final-3/cases: **0/2/0 (P -, R 0.00)**; answer (0): none
- runs/final-3/cases_no_llm: **0/2/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/2/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner_no_llm: **0/2/0 (P -, R 0.00)**; answer (0): none

### cq4 What are the direct successors of a given task?

- reference (7): (appraise property, ParallelGateway); (assess eligibility, ExclusiveGateway); (assess loan risk, ParallelGateway); (check credit history, Task, assess loan risk); (prepare acceptance pack, Task, send acceptance pack); (reject application, EndEvent); (send acceptance pack, EndEvent)
- runs/final-3/cases: **1/7/6 (P 0.17, R 0.14)**; answer (6): ((unmatched) approved loan application, Task, check credit history); ((unmatched) sent, ExclusiveGateway); (assess loan risk, ExclusiveGateway); (check credit history, Task, assess loan risk); (prepare acceptance pack, Task, (unmatched) sent); (reject application, ExclusiveGateway)
- runs/final-3/cases_no_llm: **1/7/6 (P 0.17, R 0.14)**; answer (6): ((unmatched) approved loan application, Task, check credit history); ((unmatched) sent, EndEvent); (assess loan risk, Task, reject application); (check credit history, Task, assess loan risk); (prepare acceptance pack, Task, (unmatched) sent); (reject application, Task, prepare acceptance pack)
- runs/gliner-3/cases_gliner: **1/7/5 (P 0.20, R 0.14)**; answer (5): ((unmatched) approved loan application, Task, assess eligibility); ((unmatched) sent, ExclusiveGateway); (assess eligibility, ExclusiveGateway); (prepare acceptance pack, Task, (unmatched) sent); (reject application, ExclusiveGateway)
- runs/gliner-3/cases_gliner_no_llm: **0/7/5 (P 0.00, R 0.00)**; answer (5): ((unmatched) approved loan application, Task, assess eligibility); ((unmatched) sent, EndEvent); (assess eligibility, Task, reject application); (prepare acceptance pack, Task, (unmatched) sent); (reject application, Task, prepare acceptance pack)

### cq5 Where does work pass from one participant to another?

- reference (0): none (no such construct in the model (no pair of tasks in different lanes))
- runs/final-3/cases: **n/a**; answer (2): ((unmatched) approved loan application, check credit history); (check credit history, assess loan risk)
- runs/final-3/cases_no_llm: **n/a**; answer (2): ((unmatched) approved loan application, check credit history); (check credit history, assess loan risk)
- runs/gliner-3/cases_gliner: **n/a**; answer (1): ((unmatched) approved loan application, assess eligibility)
- runs/gliner-3/cases_gliner_no_llm: **n/a**; answer (1): ((unmatched) approved loan application, assess eligibility)

### cq6 Which tasks are executed only when a condition does not hold?

- reference (2): {prepare acceptance pack, reject application}; {reject application, send acceptance pack}
- runs/final-3/cases: **1/2/2 (P 0.50, R 0.50)**; answer (2): {(unmatched) sent, reject application}; {prepare acceptance pack, reject application}
- runs/final-3/cases_no_llm: **0/2/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **1/2/2 (P 0.50, R 0.50)**; answer (2): {(unmatched) sent, reject application}; {prepare acceptance pack, reject application}
- runs/gliner-3/cases_gliner_no_llm: **0/2/0 (P -, R 0.00)**; answer (0): none

### cq7 Which tasks are performed before the first decision?

- reference (4): appraise property; assess eligibility; assess loan risk; check credit history
- runs/final-3/cases: **2/4/3 (P 0.67, R 0.50)**; answer (3): (unmatched) approved loan application; assess loan risk; check credit history
- runs/final-3/cases_no_llm: **0/4/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **1/4/2 (P 0.50, R 0.25)**; answer (2): (unmatched) approved loan application; assess eligibility
- runs/gliner-3/cases_gliner_no_llm: **0/4/0 (P -, R 0.00)**; answer (0): none

### cq8 How many tasks, decisions, parallel blocks and participants does the process have?

- reference: tasks 7, decisions 1, parallel_blocks 1, participants 0
- runs/final-3/cases: tasks 6, decisions 1, parallel_blocks 0, participants 3
- runs/final-3/cases_no_llm: tasks 6, decisions 0, parallel_blocks 0, participants 3
- runs/gliner-3/cases_gliner: tasks 5, decisions 1, parallel_blocks 0, participants 2
- runs/gliner-3/cases_gliner_no_llm: tasks 5, decisions 0, parallel_blocks 0, participants 2

## goods_dispatch

Reference: `text2bpmn/cases/goods_dispatch/reference.bpmn`.

### cq1 Which tasks does each participant (lane / HumanResource) perform?

- reference (7): (logistics, insure parcel); (secretary, clarify shipment method); (secretary, get 3 offers from logistic companies); (secretary, select logistic company and place order); (secretary, write package label); (warehouse, package goods); (warehouse, prepare for picking up goods)
- runs/final-3/cases: **2/7/10 (P 0.20, R 0.29)**; answer (10): (logistic company, (unmatched) picked up); (logistic company, prepare for picking up goods); (logistics department head, insure parcel); (secretary, (unmatched) invites); (secretary, (unmatched) selects one); (secretary, (unmatched) used post); (secretary, clarify shipment method); (secretary, write package label); (three logistic companies, (unmatched) make offers); (warehousemen, package goods)
- runs/final-3/cases_no_llm: **2/7/10 (P 0.20, R 0.29)**; answer (10): (logistic company, (unmatched) picked up); (logistic company, prepare for picking up goods); (logistics department head, insure parcel); (secretary, (unmatched) invites); (secretary, (unmatched) selects one); (secretary, (unmatched) used post); (secretary, clarify shipment method); (secretary, write package label); (three logistic companies, (unmatched) make offers); (warehousemen, package goods)
- runs/gliner-3/cases_gliner: **3/7/9 (P 0.33, R 0.43)**; answer (9): (logistic company, (unmatched) picked up); (logistic company, prepare for picking up goods); (logistics department head, insure parcel); (secretary, (unmatched) invites); (secretary, (unmatched) used normal post shipment); (secretary, clarify shipment method); (secretary, select logistic company and place order); (secretary, write package label); (warehousemen, package goods)
- runs/gliner-3/cases_gliner_no_llm: **3/7/9 (P 0.33, R 0.43)**; answer (9): (logistic company, (unmatched) picked up); (logistic company, prepare for picking up goods); (logistics department head, insure parcel); (secretary, (unmatched) invites); (secretary, (unmatched) used normal post shipment); (secretary, clarify shipment method); (secretary, select logistic company and place order); (secretary, write package label); (warehousemen, package goods)

### cq2 Which decisions does the process contain, and which task follows each outcome?

- reference (2): {get 3 offers from logistic companies, insure parcel}; {get 3 offers from logistic companies, write package label}
- runs/final-3/cases: **0/2/1 (P 0.00, R 0.00)**; answer (1): {(unmatched) invites, (unmatched) used post}
- runs/final-3/cases_no_llm: **0/2/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/2/3 (P 0.00, R 0.00)**; answer (3): {(unmatched) invites, (unmatched) used normal post shipment}; {(unmatched) invites, clarify shipment method}; {(unmatched) used normal post shipment, clarify shipment method}
- runs/gliner-3/cases_gliner_no_llm: **0/2/0 (P -, R 0.00)**; answer (0): none

### cq3 Which tasks can be executed in parallel?

- reference (5): {clarify shipment method, package goods}; {get 3 offers from logistic companies, package goods}; {insure parcel, package goods}; {package goods, select logistic company and place order}; {package goods, write package label}
- runs/final-3/cases: **0/5/1 (P 0.00, R 0.00)**; answer (1): {insure parcel, write package label}
- runs/final-3/cases_no_llm: **0/5/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/5/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner_no_llm: **0/5/0 (P -, R 0.00)**; answer (0): none

### cq4 What are the direct successors of a given task?

- reference (5): (clarify shipment method, ExclusiveGateway); (get 3 offers from logistic companies, Task, select logistic company and place order); (package goods, ExclusiveGateway); (prepare for picking up goods, EndEvent); (select logistic company and place order, ExclusiveGateway)
- runs/final-3/cases: **1/5/10 (P 0.10, R 0.20)**; answer (10): ((unmatched) invites, Task, (unmatched) make offers); ((unmatched) make offers, Task, (unmatched) selects one); ((unmatched) picked up, ExclusiveGateway); ((unmatched) selects one, ExclusiveGateway); ((unmatched) used post, ExclusiveGateway); (clarify shipment method, Task, package goods); (insure parcel, ParallelGateway); (package goods, ExclusiveGateway); (prepare for picking up goods, Task, (unmatched) picked up); (write package label, ParallelGateway)
- runs/final-3/cases_no_llm: **0/5/10 (P 0.00, R 0.00)**; answer (10): ((unmatched) invites, Task, (unmatched) make offers); ((unmatched) make offers, Task, (unmatched) selects one); ((unmatched) picked up, EndEvent); ((unmatched) selects one, Task, (unmatched) used post); ((unmatched) used post, Task, write package label); (clarify shipment method, Task, package goods); (insure parcel, Task, prepare for picking up goods); (package goods, Task, (unmatched) invites); (prepare for picking up goods, Task, (unmatched) picked up); (write package label, Task, insure parcel)
- runs/gliner-3/cases_gliner: **2/5/9 (P 0.22, R 0.40)**; answer (9): ((unmatched) invites, Task, select logistic company and place order); ((unmatched) picked up, ExclusiveGateway); ((unmatched) used normal post shipment, ExclusiveGateway); (clarify shipment method, Task, package goods); (insure parcel, ExclusiveGateway); (package goods, ExclusiveGateway); (prepare for picking up goods, Task, (unmatched) picked up); (select logistic company and place order, ExclusiveGateway); (write package label, Task, insure parcel)
- runs/gliner-3/cases_gliner_no_llm: **0/5/9 (P 0.00, R 0.00)**; answer (9): ((unmatched) invites, Task, select logistic company and place order); ((unmatched) picked up, EndEvent); ((unmatched) used normal post shipment, Task, write package label); (clarify shipment method, Task, package goods); (insure parcel, Task, prepare for picking up goods); (package goods, Task, (unmatched) invites); (prepare for picking up goods, Task, (unmatched) picked up); (select logistic company and place order, Task, (unmatched) used normal post shipment); (write package label, Task, insure parcel)

### cq5 Where does work pass from one participant to another?

- reference (4): (clarify shipment method, insure parcel); (insure parcel, prepare for picking up goods); (select logistic company and place order, prepare for picking up goods); (write package label, prepare for picking up goods)
- runs/final-3/cases: **2/4/9 (P 0.22, R 0.50)**; answer (9): ((unmatched) invites, (unmatched) make offers); ((unmatched) make offers, (unmatched) selects one); ((unmatched) selects one, insure parcel); ((unmatched) used post, insure parcel); (clarify shipment method, package goods); (insure parcel, prepare for picking up goods); (package goods, (unmatched) invites); (package goods, (unmatched) used post); (write package label, prepare for picking up goods)
- runs/final-3/cases_no_llm: **1/4/6 (P 0.17, R 0.25)**; answer (6): ((unmatched) invites, (unmatched) make offers); ((unmatched) make offers, (unmatched) selects one); (clarify shipment method, package goods); (insure parcel, prepare for picking up goods); (package goods, (unmatched) invites); (write package label, insure parcel)
- runs/gliner-3/cases_gliner: **1/4/5 (P 0.20, R 0.25)**; answer (5): (clarify shipment method, package goods); (insure parcel, prepare for picking up goods); (package goods, (unmatched) invites); (package goods, (unmatched) used normal post shipment); (write package label, insure parcel)
- runs/gliner-3/cases_gliner_no_llm: **1/4/4 (P 0.25, R 0.25)**; answer (4): (clarify shipment method, package goods); (insure parcel, prepare for picking up goods); (package goods, (unmatched) invites); (write package label, insure parcel)

### cq6 Which tasks are executed only when a condition does not hold?

- reference (4): {get 3 offers from logistic companies, insure parcel}; {get 3 offers from logistic companies, write package label}; {insure parcel, select logistic company and place order}; {select logistic company and place order, write package label}
- runs/final-3/cases: **0/4/3 (P 0.00, R 0.00)**; answer (3): {(unmatched) invites, (unmatched) used post}; {(unmatched) make offers, (unmatched) used post}; {(unmatched) selects one, (unmatched) used post}
- runs/final-3/cases_no_llm: **0/4/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/4/2 (P 0.00, R 0.00)**; answer (2): {(unmatched) invites, (unmatched) used normal post shipment}; {(unmatched) used normal post shipment, select logistic company and place order}
- runs/gliner-3/cases_gliner_no_llm: **0/4/0 (P -, R 0.00)**; answer (0): none

### cq7 Which tasks are performed before the first decision?

- reference (1): clarify shipment method
- runs/final-3/cases: **1/1/2 (P 0.50, R 1.00)**; answer (2): clarify shipment method; package goods
- runs/final-3/cases_no_llm: **0/1/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/1/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner_no_llm: **0/1/0 (P -, R 0.00)**; answer (0): none

### cq8 How many tasks, decisions, parallel blocks and participants does the process have?

- reference: tasks 7, decisions 1, parallel_blocks 1, participants 3
- runs/final-3/cases: tasks 10, decisions 2, parallel_blocks 1, participants 5
- runs/final-3/cases_no_llm: tasks 10, decisions 0, parallel_blocks 0, participants 5
- runs/gliner-3/cases_gliner: tasks 9, decisions 3, parallel_blocks 0, participants 4
- runs/gliner-3/cases_gliner_no_llm: tasks 9, decisions 0, parallel_blocks 0, participants 4

## healthcare

Reference: `text2bpmn/cases/healthcare/reference.bpmn`.

### cq1 Which tasks does each participant (lane / HumanResource) perform?

- reference (23): (emergency department, evaluate patient); (family, family calls 112); (family, patient calls 112); (family, present directly to ed); (general practitioner, adjust initiate treatment); (general practitioner, recommend cardiological evaluation); (general practitioner, refer to outpatient cardiologist); (general practitioner, visit gp); (hospital, admit urgent hospitalization); (hospital, complete treatment); (hospital, establish final diagnosis); (hospital, interventional treatment); (hospital, maintain communication); (hospital, medical treatment); (hospital, prepare discharge); (hospital, surgical treatment); (outpatient cardiology, consult private cardiologist); (outpatient cardiology, perform evaluation); (outpatient cardiology, prescribe treatment and followups); (outpatient cardiology, provide summary); (patient, family provides history); (patient, provide medical history); (patient, submit summary to gp)
- runs/final-3/cases: **8/23/32 (P 0.25, R 0.35)**; answer (32): (emergency department, interventional treatment); (emergency department, perform evaluation); (emergency services, (unmatched) presents); (family, (unmatched) inform); (family, provide medical history); (general practitioner, (unmatched) initiates); (general practitioner, (unmatched) managed); (general practitioner, (unmatched) referred); (general practitioner, adjust initiate treatment); (general practitioner, recommend cardiological evaluation); (hospital, (unmatched) administers); (hospital, maintain communication); (hospital, prepare discharge); (outpatient cardiology, (unmatched) decide); (outpatient cardiology, (unmatched) gathered medical history); (outpatient cardiology, consult private cardiologist); (outpatient cardiology, establish final diagnosis); (outpatient cardiology, evaluate patient); (outpatient cardiology, prescribe treatment and followups); (outpatient cardiology, visit gp); (patient's family, (unmatched) contacts); (patient, (unmatched) choose); (patient, (unmatched) concludes); (patient, (unmatched) develops); (patient, (unmatched) follow up); (patient, (unmatched) make triage decision); (patient, (unmatched) takes); (patient, admit urgent hospitalization); (patient, family provides history); (patient, patient calls 112); (patient, provide summary); (patient, submit summary to gp)
- runs/final-3/cases_no_llm: **8/23/32 (P 0.25, R 0.35)**; answer (32): (emergency department, interventional treatment); (emergency department, perform evaluation); (emergency services, (unmatched) presents); (family, (unmatched) inform); (family, provide medical history); (general practitioner, (unmatched) initiates); (general practitioner, (unmatched) managed); (general practitioner, (unmatched) referred); (general practitioner, adjust initiate treatment); (general practitioner, recommend cardiological evaluation); (hospital, (unmatched) administers); (hospital, maintain communication); (hospital, prepare discharge); (outpatient cardiology, (unmatched) decide); (outpatient cardiology, (unmatched) gathered medical history); (outpatient cardiology, consult private cardiologist); (outpatient cardiology, establish final diagnosis); (outpatient cardiology, evaluate patient); (outpatient cardiology, prescribe treatment and followups); (outpatient cardiology, visit gp); (patient's family, (unmatched) contacts); (patient, (unmatched) choose); (patient, (unmatched) concludes); (patient, (unmatched) develops); (patient, (unmatched) follow up); (patient, (unmatched) make triage decision); (patient, (unmatched) takes); (patient, admit urgent hospitalization); (patient, family provides history); (patient, patient calls 112); (patient, provide summary); (patient, submit summary to gp)
- runs/gliner-3/cases_gliner: **8/23/28 (P 0.29, R 0.35)**; answer (28): (emergency department, admit urgent hospitalization); (emergency department, evaluate patient); (emergency department, medical treatment); (emergency services, (unmatched) contacts); (emergency services, (unmatched) presents); (family, family provides history); (family, refer to outpatient cardiologist); (general practitioner, (unmatched) managed follow up care); (general practitioner, (unmatched) referred patient); (general practitioner, adjust initiate treatment); (general practitioner, recommend cardiological evaluation); (general practitioner, visit gp); (hospital, (unmatched) administers); (hospital, maintain communication); (hospital, prepare discharge); (outpatient cardiology, (unmatched) admitted); (outpatient cardiology, (unmatched) assessing); (outpatient cardiology, (unmatched) consult); (outpatient cardiology, (unmatched) decide); (outpatient cardiology, (unmatched) gathered medical history); (outpatient cardiology, (unmatched) recommend); (outpatient cardiology, establish final diagnosis); (outpatient cardiology, patient calls 112); (patient, (unmatched) takes non emergency route); (patient, consult private cardiologist); (patient, family provides history); (patient, provide summary); (patient, submit summary to gp)
- runs/gliner-3/cases_gliner_no_llm: **8/23/28 (P 0.29, R 0.35)**; answer (28): (emergency department, admit urgent hospitalization); (emergency department, evaluate patient); (emergency department, medical treatment); (emergency services, (unmatched) contacts); (emergency services, (unmatched) presents); (family, family provides history); (family, refer to outpatient cardiologist); (general practitioner, (unmatched) managed follow up care); (general practitioner, (unmatched) referred patient); (general practitioner, adjust initiate treatment); (general practitioner, recommend cardiological evaluation); (general practitioner, visit gp); (hospital, (unmatched) administers); (hospital, maintain communication); (hospital, prepare discharge); (outpatient cardiology, (unmatched) admitted); (outpatient cardiology, (unmatched) assessing); (outpatient cardiology, (unmatched) consult); (outpatient cardiology, (unmatched) decide); (outpatient cardiology, (unmatched) gathered medical history); (outpatient cardiology, (unmatched) recommend); (outpatient cardiology, establish final diagnosis); (outpatient cardiology, patient calls 112); (patient, (unmatched) takes non emergency route); (patient, consult private cardiologist); (patient, family provides history); (patient, provide summary); (patient, submit summary to gp)

### cq2 Which decisions does the process contain, and which task follows each outcome?

- reference (17): {adjust initiate treatment, admit urgent hospitalization}; {adjust initiate treatment, refer to outpatient cardiologist}; {admit urgent hospitalization, refer to outpatient cardiologist}; {consult private cardiologist, family calls 112}; {consult private cardiologist, patient calls 112}; {consult private cardiologist, present directly to ed}; {consult private cardiologist, visit gp}; {family calls 112, patient calls 112}; {family calls 112, present directly to ed}; {family calls 112, visit gp}; {family provides history, provide medical history}; {interventional treatment, medical treatment}; {interventional treatment, surgical treatment}; {medical treatment, surgical treatment}; {patient calls 112, present directly to ed}; {patient calls 112, visit gp}; {present directly to ed, visit gp}
- runs/final-3/cases: **0/17/3 (P 0.00, R 0.00)**; answer (3): {(unmatched) contacts, perform evaluation}; {(unmatched) managed, (unmatched) takes}; {(unmatched) takes, consult private cardiologist}
- runs/final-3/cases_no_llm: **0/17/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/17/5 (P 0.00, R 0.00)**; answer (5): {(unmatched) assessing, consult private cardiologist}; {(unmatched) contacts, evaluate patient}; {(unmatched) managed follow up care, (unmatched) referred patient}; {(unmatched) managed follow up care, medical treatment}; {(unmatched) referred patient, medical treatment}
- runs/gliner-3/cases_gliner_no_llm: **0/17/0 (P -, R 0.00)**; answer (0): none

### cq3 Which tasks can be executed in parallel?

- reference (4): {complete treatment, maintain communication}; {interventional treatment, maintain communication}; {maintain communication, medical treatment}; {maintain communication, surgical treatment}
- runs/final-3/cases: **0/4/0 (P -, R 0.00)**; answer (0): none
- runs/final-3/cases_no_llm: **0/4/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/4/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner_no_llm: **0/4/0 (P -, R 0.00)**; answer (0): none

### cq4 What are the direct successors of a given task?

- reference (23): (adjust initiate treatment, Task, recommend cardiological evaluation); (admit urgent hospitalization, ExclusiveGateway); (complete treatment, ParallelGateway); (consult private cardiologist, Task, perform evaluation); (establish final diagnosis, ParallelGateway); (evaluate patient, ExclusiveGateway); (family calls 112, ExclusiveGateway); (family provides history, ExclusiveGateway); (interventional treatment, ExclusiveGateway); (maintain communication, ParallelGateway); (medical treatment, ExclusiveGateway); (patient calls 112, ExclusiveGateway); (perform evaluation, Task, prescribe treatment and followups); (prepare discharge, Task, provide summary); (prescribe treatment and followups, ExclusiveGateway); (present directly to ed, Task, evaluate patient); (provide medical history, ExclusiveGateway); (provide summary, Task, submit summary to gp); (recommend cardiological evaluation, Task, perform evaluation); (refer to outpatient cardiologist, Task, perform evaluation); (submit summary to gp, EndEvent); (surgical treatment, ExclusiveGateway); (visit gp, Task, adjust initiate treatment)
- runs/final-3/cases: **2/23/32 (P 0.06, R 0.09)**; answer (32): ((unmatched) administers, Task, maintain communication); ((unmatched) choose, ExclusiveGateway); ((unmatched) concludes, Task, submit summary to gp); ((unmatched) contacts, Task, (unmatched) presents); ((unmatched) decide, Task, evaluate patient); ((unmatched) develops, ExclusiveGateway); ((unmatched) follow up, Task, (unmatched) concludes); ((unmatched) gathered medical history, Task, family provides history); ((unmatched) inform, Task, prepare discharge); ((unmatched) initiates, Task, recommend cardiological evaluation); ((unmatched) make triage decision, Task, admit urgent hospitalization); ((unmatched) managed, Task, (unmatched) referred); ((unmatched) presents, ExclusiveGateway); ((unmatched) referred, ExclusiveGateway); ((unmatched) takes, Task, adjust initiate treatment); (adjust initiate treatment, Task, (unmatched) initiates); (admit urgent hospitalization, Task, interventional treatment); (consult private cardiologist, Task, establish final diagnosis); (establish final diagnosis, Task, prescribe treatment and followups); (evaluate patient, Task, (unmatched) gathered medical history); (family provides history, Task, provide medical history); (interventional treatment, ExclusiveGateway); (maintain communication, Task, (unmatched) inform); (patient calls 112, EndEvent); (perform evaluation, Task, (unmatched) make triage decision); (prepare discharge, Task, provide summary); (prescribe treatment and followups, Task, visit gp); (provide medical history, Task, (unmatched) administers); (provide summary, Task, (unmatched) follow up); (recommend cardiological evaluation, Task, (unmatched) choose); (submit summary to gp, Task, patient calls 112); (visit gp, Task, (unmatched) decide)
- runs/final-3/cases_no_llm: **1/23/32 (P 0.03, R 0.04)**; answer (32): ((unmatched) administers, Task, maintain communication); ((unmatched) choose, Task, consult private cardiologist); ((unmatched) concludes, Task, submit summary to gp); ((unmatched) contacts, Task, (unmatched) presents); ((unmatched) decide, Task, evaluate patient); ((unmatched) develops, Task, (unmatched) contacts); ((unmatched) follow up, Task, (unmatched) concludes); ((unmatched) gathered medical history, Task, family provides history); ((unmatched) inform, Task, prepare discharge); ((unmatched) initiates, Task, recommend cardiological evaluation); ((unmatched) make triage decision, Task, admit urgent hospitalization); ((unmatched) managed, Task, (unmatched) referred); ((unmatched) presents, Task, perform evaluation); ((unmatched) referred, Task, (unmatched) takes); ((unmatched) takes, Task, adjust initiate treatment); (adjust initiate treatment, Task, (unmatched) initiates); (admit urgent hospitalization, Task, interventional treatment); (consult private cardiologist, Task, establish final diagnosis); (establish final diagnosis, Task, prescribe treatment and followups); (evaluate patient, Task, (unmatched) gathered medical history); (family provides history, Task, provide medical history); (interventional treatment, Task, (unmatched) managed); (maintain communication, Task, (unmatched) inform); (patient calls 112, EndEvent); (perform evaluation, Task, (unmatched) make triage decision); (prepare discharge, Task, provide summary); (prescribe treatment and followups, Task, visit gp); (provide medical history, Task, (unmatched) administers); (provide summary, Task, (unmatched) follow up); (recommend cardiological evaluation, Task, (unmatched) choose); (submit summary to gp, Task, patient calls 112); (visit gp, Task, (unmatched) decide)
- runs/gliner-3/cases_gliner: **7/23/28 (P 0.25, R 0.30)**; answer (28): ((unmatched) administers, Task, maintain communication); ((unmatched) admitted, Task, (unmatched) gathered medical history); ((unmatched) assessing, Task, (unmatched) decide); ((unmatched) consult, Task, establish final diagnosis); ((unmatched) contacts, Task, (unmatched) presents); ((unmatched) decide, Task, (unmatched) recommend); ((unmatched) gathered medical history, Task, family provides history); ((unmatched) managed follow up care, ExclusiveGateway); ((unmatched) presents, ExclusiveGateway); ((unmatched) recommend, Task, patient calls 112); ((unmatched) referred patient, ExclusiveGateway); ((unmatched) takes non emergency route, Task, visit gp); (adjust initiate treatment, Task, recommend cardiological evaluation); (admit urgent hospitalization, ExclusiveGateway); (consult private cardiologist, Task, (unmatched) consult); (establish final diagnosis, ExclusiveGateway); (evaluate patient, Task, admit urgent hospitalization); (family provides history, Task, (unmatched) administers); (family provides history, Task, family provides history); (maintain communication, Task, refer to outpatient cardiologist); (medical treatment, ExclusiveGateway); (patient calls 112, Task, (unmatched) admitted); (prepare discharge, Task, provide summary); (provide summary, Task, submit summary to gp); (recommend cardiological evaluation, ExclusiveGateway); (refer to outpatient cardiologist, Task, prepare discharge); (submit summary to gp, EndEvent); (visit gp, Task, adjust initiate treatment)
- runs/gliner-3/cases_gliner_no_llm: **5/23/28 (P 0.18, R 0.22)**; answer (28): ((unmatched) administers, Task, maintain communication); ((unmatched) admitted, Task, (unmatched) gathered medical history); ((unmatched) assessing, Task, (unmatched) decide); ((unmatched) consult, Task, establish final diagnosis); ((unmatched) contacts, Task, (unmatched) presents); ((unmatched) decide, Task, (unmatched) recommend); ((unmatched) gathered medical history, Task, family provides history); ((unmatched) managed follow up care, Task, (unmatched) referred patient); ((unmatched) presents, Task, evaluate patient); ((unmatched) recommend, Task, patient calls 112); ((unmatched) referred patient, Task, (unmatched) takes non emergency route); ((unmatched) takes non emergency route, Task, visit gp); (adjust initiate treatment, Task, recommend cardiological evaluation); (admit urgent hospitalization, Task, medical treatment); (consult private cardiologist, Task, (unmatched) consult); (establish final diagnosis, Task, (unmatched) assessing); (evaluate patient, Task, admit urgent hospitalization); (family provides history, Task, (unmatched) administers); (family provides history, Task, family provides history); (maintain communication, Task, refer to outpatient cardiologist); (medical treatment, Task, (unmatched) managed follow up care); (patient calls 112, Task, (unmatched) admitted); (prepare discharge, Task, provide summary); (provide summary, Task, submit summary to gp); (recommend cardiological evaluation, Task, consult private cardiologist); (refer to outpatient cardiologist, Task, prepare discharge); (submit summary to gp, EndEvent); (visit gp, Task, adjust initiate treatment)

### cq5 Where does work pass from one participant to another?

- reference (14): (admit urgent hospitalization, family provides history); (admit urgent hospitalization, provide medical history); (evaluate patient, adjust initiate treatment); (evaluate patient, refer to outpatient cardiologist); (family calls 112, evaluate patient); (family provides history, establish final diagnosis); (patient calls 112, evaluate patient); (prepare discharge, provide summary); (prescribe treatment and followups, admit urgent hospitalization); (present directly to ed, evaluate patient); (provide medical history, establish final diagnosis); (provide summary, submit summary to gp); (recommend cardiological evaluation, perform evaluation); (refer to outpatient cardiologist, perform evaluation)
- runs/final-3/cases: **1/14/16 (P 0.06, R 0.07)**; answer (16): ((unmatched) choose, consult private cardiologist); ((unmatched) contacts, (unmatched) presents); ((unmatched) develops, (unmatched) contacts); ((unmatched) gathered medical history, family provides history); ((unmatched) inform, prepare discharge); ((unmatched) presents, perform evaluation); ((unmatched) referred, (unmatched) takes); ((unmatched) takes, adjust initiate treatment); (admit urgent hospitalization, interventional treatment); (family provides history, provide medical history); (interventional treatment, (unmatched) managed); (maintain communication, (unmatched) inform); (perform evaluation, (unmatched) make triage decision); (prepare discharge, provide summary); (provide medical history, (unmatched) administers); (recommend cardiological evaluation, (unmatched) choose)
- runs/final-3/cases_no_llm: **1/14/16 (P 0.06, R 0.07)**; answer (16): ((unmatched) choose, consult private cardiologist); ((unmatched) contacts, (unmatched) presents); ((unmatched) develops, (unmatched) contacts); ((unmatched) gathered medical history, family provides history); ((unmatched) inform, prepare discharge); ((unmatched) presents, perform evaluation); ((unmatched) referred, (unmatched) takes); ((unmatched) takes, adjust initiate treatment); (admit urgent hospitalization, interventional treatment); (family provides history, provide medical history); (interventional treatment, (unmatched) managed); (maintain communication, (unmatched) inform); (perform evaluation, (unmatched) make triage decision); (prepare discharge, provide summary); (provide medical history, (unmatched) administers); (recommend cardiological evaluation, (unmatched) choose)
- runs/gliner-3/cases_gliner: **1/14/15 (P 0.07, R 0.07)**; answer (15): ((unmatched) gathered medical history, family provides history); ((unmatched) managed follow up care, (unmatched) takes non emergency route); ((unmatched) presents, evaluate patient); ((unmatched) referred patient, (unmatched) takes non emergency route); ((unmatched) takes non emergency route, visit gp); (admit urgent hospitalization, (unmatched) managed follow up care); (admit urgent hospitalization, (unmatched) referred patient); (consult private cardiologist, (unmatched) consult); (family provides history, (unmatched) administers); (family provides history, family provides history); (maintain communication, refer to outpatient cardiologist); (medical treatment, (unmatched) takes non emergency route); (prepare discharge, provide summary); (recommend cardiological evaluation, consult private cardiologist); (refer to outpatient cardiologist, prepare discharge)
- runs/gliner-3/cases_gliner_no_llm: **1/14/12 (P 0.08, R 0.07)**; answer (12): ((unmatched) gathered medical history, family provides history); ((unmatched) presents, evaluate patient); ((unmatched) referred patient, (unmatched) takes non emergency route); ((unmatched) takes non emergency route, visit gp); (consult private cardiologist, (unmatched) consult); (family provides history, (unmatched) administers); (family provides history, family provides history); (maintain communication, refer to outpatient cardiologist); (medical treatment, (unmatched) managed follow up care); (prepare discharge, provide summary); (recommend cardiological evaluation, consult private cardiologist); (refer to outpatient cardiologist, prepare discharge)

### cq6 Which tasks are executed only when a condition does not hold?

- reference (16): {adjust initiate treatment, refer to outpatient cardiologist}; {consult private cardiologist, family calls 112}; {consult private cardiologist, patient calls 112}; {consult private cardiologist, present directly to ed}; {consult private cardiologist, visit gp}; {family calls 112, patient calls 112}; {family calls 112, present directly to ed}; {family calls 112, visit gp}; {family provides history, provide medical history}; {interventional treatment, medical treatment}; {interventional treatment, surgical treatment}; {medical treatment, surgical treatment}; {patient calls 112, present directly to ed}; {patient calls 112, visit gp}; {present directly to ed, visit gp}; {recommend cardiological evaluation, refer to outpatient cardiologist}
- runs/final-3/cases: **0/16/0 (P -, R 0.00)**; answer (0): none
- runs/final-3/cases_no_llm: **0/16/0 (P -, R 0.00)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/16/3 (P 0.00, R 0.00)**; answer (3): {(unmatched) managed follow up care, (unmatched) referred patient}; {(unmatched) managed follow up care, medical treatment}; {(unmatched) referred patient, medical treatment}
- runs/gliner-3/cases_gliner_no_llm: **0/16/0 (P -, R 0.00)**; answer (0): none

### cq7 Which tasks are performed before the first decision?

- reference (0): none (the model has a decision (exclusive split) and the graph holds what the query reads, but no row satisfies the question)
- runs/final-3/cases: **0/0/1 (P 0.00, R -)**; answer (1): (unmatched) develops
- runs/final-3/cases_no_llm: **0/0/0 (P -, R -)**; answer (0): none
- runs/gliner-3/cases_gliner: **0/0/0 (P -, R -)**; answer (0): none
- runs/gliner-3/cases_gliner_no_llm: **0/0/0 (P -, R -)**; answer (0): none

### cq8 How many tasks, decisions, parallel blocks and participants does the process have?

- reference: tasks 23, decisions 7, parallel_blocks 1, participants 6
- runs/final-3/cases: tasks 32, decisions 3, parallel_blocks 0, participants 8
- runs/final-3/cases_no_llm: tasks 32, decisions 0, parallel_blocks 0, participants 8
- runs/gliner-3/cases_gliner: tasks 28, decisions 3, parallel_blocks 0, participants 7
- runs/gliner-3/cases_gliner_no_llm: tasks 28, decisions 0, parallel_blocks 0, participants 7
