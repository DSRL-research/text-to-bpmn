The pipeline's edges against PET's `flow` relations, 45 documents, PET's gold entity spans as input and the real relation classifier, 84 calls.

Recall is the share of annotated flows the pipeline builds; an edge counts when it is direct or passes through one gateway.

| Flow shape | built | missed | recall |
|---|---|---|---|
| sequence | 301 | 20 | 0.938 |
| into a decision | 45 | 24 | 0.652 |
| out of a branch | 68 | 10 | 0.872 |
| **all shapes** | 414 | 54 | **0.885** |

Edges the pipeline adds between annotated elements that PET does not annotate: 194, giving precision 0.681 and F1 0.77.

Gold edges whose endpoints could not be mapped to an element: 23.

On every PET flow but the condition folding (the second measure): 485 built, 84 missed, 118 not annotated, 21 unmapped; precision 0.804, recall 0.852, F1 0.828.

Pairs of steps PET puts in parallel lines of work (the third measure): 5 built side by side, 5 not, 1 side by side where PET has no such pair, 0 gold targets unmapped.

The relation classifier was asked 84 times and answered 84 of them; 0 calls failed (0.0%). A failed call returns UNKNOWN and no edge is built, so those land as missing flows: the recall above is the deployed system's, and it charges the pipeline for answers the model never gave. See provenance/relation_failures_2026-10-07.md.

Examples of flows the pipeline does not build:
- doc-2.1: 'In case the customer is of certain significance' -> 'Determines the significance of the customer' (out of a branch)
- doc-2.1: 'Sent back the actual service performance' -> 'Receives the actual service performance' (sequence)
- doc-2.1: 'Sent out' -> 'Receives the actual service performance' (sequence)
- doc-2.1: 'Adjust the billing' -> 'Sent out the report' (sequence)
- doc-4.1: 'Recorded the assignments' -> 'Determined the medical file of the patient' (sequence)
- doc-4.1: 'Added the standard checklist' -> 'If required has been received' (into a decision)
- doc-4.1: 'If required has been received' -> 'Plans the first meeting' (out of a branch)
- doc-2.2: 'Generated the contract documents' -> 'Check the contract documents' (sequence)
- doc-6.1: 'Received these' -> 'Inspection' (sequence)
- doc-6.1: 'Forwarded' -> 'Identifies the charging suppliers' (sequence)
- doc-6.1: 'Inspection' -> 'Forwarded' (sequence)
- doc-6.1: 'Sent the docket and the copy of the invoice' -> 'Receiving the copy of the invoice' (sequence)
