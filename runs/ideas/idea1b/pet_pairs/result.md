The pipeline's edges against PET's `flow` relations, 45 documents, PET's gold entity spans as input and the real relation classifier, 1300 calls.

Recall is the share of annotated flows the pipeline builds; an edge counts when it is direct or passes through one gateway.

| Flow shape | built | missed | recall |
|---|---|---|---|
| sequence | 247 | 74 | 0.769 |
| into a decision | 41 | 29 | 0.586 |
| out of a branch | 66 | 12 | 0.846 |
| **all shapes** | 354 | 115 | **0.755** |

Edges the pipeline adds between annotated elements that PET does not annotate: 152, giving precision 0.7 and F1 0.726.

Gold edges whose endpoints could not be mapped to an element: 22.

On every PET flow but the condition folding (the second measure): 400 built, 179 missed, 101 not annotated, 15 unmapped; precision 0.798, recall 0.691, F1 0.741.

The relation classifier was asked 1300 times and answered 1300 of them; 0 calls failed (0.0%). A failed call returns UNKNOWN and no edge is built, so those land as missing flows: the recall above is the deployed system's, and it charges the pipeline for answers the model never gave. See provenance/relation_failures_2026-10-07.md.

Examples of flows the pipeline does not build:
- doc-2.1: 'In case the customer is of certain significance' -> 'Determines the significance of the customer' (out of a branch)
- doc-2.1: 'Sent out the detailed problem report' -> 'Receives the detailed problem report' (sequence)
- doc-2.1: 'Created a notification' -> 'Included a status report' (sequence)
- doc-2.1: 'Analyzed this' -> 'Created a trouble report' (sequence)
- doc-2.1: 'Sent back the actual service performance' -> 'Receives the actual service performance' (sequence)
- doc-2.1: 'Created the problem resolution report' -> 'Sent out' (sequence)
- doc-2.1: 'Sent out' -> 'Receives the actual service performance' (sequence)
- doc-2.1: 'Created a report' -> 'Sent out the report' (sequence)
- doc-2.1: 'Reported an SLA violation rebate' -> 'Adjust the billing' (sequence)
- doc-2.1: 'Adjust the billing' -> 'Sent out the report' (sequence)
- doc-4.1: 'Created a patient file' -> 'Stored the print from the information system' (sequence)
- doc-4.1: 'Recorded the assignments' -> 'Determined the medical file of the patient' (sequence)
