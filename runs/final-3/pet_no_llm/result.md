The pipeline's edges against PET's `flow` relations, 45 documents, PET's gold entity spans as input and the real relation classifier, 1593 calls.

Recall is the share of annotated flows the pipeline builds; an edge counts when it is direct or passes through one gateway.

| Flow shape | built | missed | recall |
|---|---|---|---|
| sequence | 285 | 36 | 0.888 |
| into a decision | 44 | 32 | 0.579 |
| out of a branch | 68 | 10 | 0.872 |
| **all shapes** | 397 | 78 | **0.836** |

Edges the pipeline adds between annotated elements that PET does not annotate: 170, giving precision 0.7 and F1 0.762.

Gold edges whose endpoints could not be mapped to an element: 16.

On every PET flow but the condition folding (the second measure): 450 built, 129 missed, 115 not annotated, 15 unmapped; precision 0.796, recall 0.777, F1 0.787.

Pairs of steps PET puts in parallel lines of work (the third measure): 0 built side by side, 10 not, 0 side by side where PET has no such pair, 0 gold targets unmapped.

The relation classifier was asked 1593 times and answered 0 of them; 1593 calls failed (100.0%). A failed call returns UNKNOWN and no edge is built, so those land as missing flows: the recall above is the deployed system's, and it charges the pipeline for answers the model never gave. See provenance/relation_failures_2026-10-07.md.

Examples of flows the pipeline does not build:
- doc-2.1: 'In case the customer is of certain significance' -> 'Determines the significance of the customer' (out of a branch)
- doc-2.1: 'Sent out the detailed problem report' -> 'Receives the detailed problem report' (sequence)
- doc-2.1: 'Created a notification' -> 'Included a status report' (sequence)
- doc-2.1: 'Sent back the actual service performance' -> 'Receives the actual service performance' (sequence)
- doc-2.1: 'Sent out' -> 'Receives the actual service performance' (sequence)
- doc-2.1: 'Created a report' -> 'Sent out the report' (sequence)
- doc-4.1: 'Recorded the assignments' -> 'Determined the medical file of the patient' (sequence)
- doc-4.1: 'Added the standard checklist' -> 'If required has been received' (into a decision)
- doc-4.1: 'If required has been received' -> 'Plans the first meeting' (out of a branch)
- doc-2.2: 'Generated the contract documents' -> 'Check the contract documents' (sequence)
- doc-2.2: 'Sends it' -> 'Receiving the meter data' (sequence)
- doc-6.1: 'Received these' -> 'Inspection' (sequence)
