# Window coverage of PET's gold flow relations

Run 2026-11-02T09:47:11+00:00 at revision-final-7-gd00a9a6 (d00a9a6, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.5.0, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.dev0.

675 flow relations in 45 documents; 675 have both ends on a gold span (0 have a head token that starts no span and are left out). The PET paper counts 689; the released PETv1.1 file read here has 675, and differs from the paper in nearly every relation type, so the gap is the dataset version.

## Ordering: all behavioural mentions

675 flows used.

| distance | flows | share |
|---|---|---|
| 1 | 535 | 79.3% |
| 2 | 40 | 5.9% |
| 3 | 25 | 3.7% |
| >3 | 32 | 4.7% |
| backward | 43 | 6.4% |
| same mention | 0 | 0.0% |

Within the window (forward, 1 to 3): 600 of 675 (88.9%).

Backward flows by head and tail type: XOR Gateway -> Activity 21, Activity -> Activity 8, AND Gateway -> Activity 5, Condition Specification -> Activity 5, XOR Gateway -> Condition Specification 4.

Backward, first three:

- doc-10.1: 'or' (XOR Gateway) -> 'opposes' (Activity), distance -1
- doc-10.12: 'or' (XOR Gateway) -> 'confirmes' (Activity), distance -1
- doc-1.2: 'whereas' (AND Gateway) -> 'check' (Activity), distance -2

## Ordering: Condition Specification folded into its gateway, as the pipeline does

675 flows used.

| distance | flows | share |
|---|---|---|
| 1 | 461 | 68.3% |
| 2 | 49 | 7.3% |
| 3 | 19 | 2.8% |
| >3 | 27 | 4.0% |
| backward | 43 | 6.4% |
| same mention | 76 | 11.3% |

Within the window (forward, 1 to 3): 529 of 675 (78.4%).
Leaving out the 76 flows from a gateway to its own folded condition, which need no relation: 529 of 599 (88.3%).

The same 599 flows by distance, shares summing to 100%:

| distance | flows | share |
|---|---|---|
| 1 | 461 | 77.0% |
| 2 | 49 | 8.2% |
| 3 | 19 | 3.2% |
| >3 | 27 | 4.5% |
| backward | 43 | 7.2% |

Backward flows by head and tail type: XOR Gateway -> Activity 21, Activity -> Activity 8, AND Gateway -> Activity 5, Condition Specification -> Activity 5, XOR Gateway -> Condition Specification 4.

Backward, first three:

- doc-10.1: 'or' (XOR Gateway) -> 'opposes' (Activity), distance -1
- doc-10.12: 'or' (XOR Gateway) -> 'confirmes' (Activity), distance -1
- doc-1.2: 'whereas' (AND Gateway) -> 'check' (Activity), distance -2
