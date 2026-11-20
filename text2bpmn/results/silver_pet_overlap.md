# The 302-pair set against PET

`python3 -m text2bpmn.checks.silver_pet_overlap` (text2bpmn/checks/silver_pet_overlap.py, SHA-256 `439de9405a7e9197…`). Inputs, SHA-256:

- `benchmark_silver_2.jsonl` `1092a8301ce92ec1b9cf7db1809aebccecce99e520ad709e6d0135dbed6bc3c9`
- `pet_data/PETv1.1-relations.json` `bfb71816cc9782cb7197f106643935bd973a8376ca736db51e28f8e72b8d9708`
- `pet_train.json` `398768f0e7d351e454f1eed85562603590fc24e8559317a5a53768035062d21d`
- `pet_test.json` `489a7bb34cbd3112f99a61cc35b4cdcfd2dd3e3d108917faa194504bfa68fdf0`

The set: 302 pairs from 185 distinct fragments. PET: 45 documents, 417 sentences (`pet_train.json` and `pet_test.json` hold the same sentences as `pet_data/PETv1.1-relations.json`), 1832 relations. Words are lower-cased `\w+` tokens.

## Exact and near-duplicate matches

| measure | fragments |
|---|---|
| fragment found verbatim in a PET document | 0 |
| fragment with a sentence equal to a PET sentence | 0 |
| fragment sharing at least one word 8-gram with PET | 0 (of 185 with 8 words or more) |
| highest similarity to a PET window at least 0.4 | 29 |
| highest similarity to a PET window at least 0.3 | 159 |

Highest similarity: SequenceMatcher ratio over words against every window of 1, 2, 3 consecutive sentences of one PET document; the fragments with the highest values, then every fragment sharing an 8-gram:

| # | fragment | pairs | similarity | longest shared run (words) | 8-grams in PET | PET window |
|---|---|---|---|---|---|---|
| 95 | If the humidity is high, enable the dehumidifier. Else, do nothing. | 3 | 0.476 | 2 | 0/4 | doc-5.1, sentence 3: If the customer is high risk , the loan is denied . |
| 162 | The user inputs the OTP. The app verifies the code. | 1 | 0.476 | 2 | 0/3 | doc-10.8, sentence 0-1: The MSPO deregisters at the GO . The GO verifies the deregistration . |
| 32 | The technician reboots the router and checks the signal strength. | 1 | 0.455 | 3 | 0/3 | doc-3.8, sentence 2: Then , the Handling department picks up the claim and checks the insurance . |
| 40 | The cashier scans the items and accepts the payment. | 1 | 0.455 | 2 | 0/2 | doc-3.5, sentence 8: Meantime , the Cashier captures the Party Details and prints the Physical Court File . |
| 133 | If the email is marked as spam, move it to the junk folder. Else, leave it in the inbox. | 3 | 0.450 | 3 | 0/12 | doc-3.3, sentence 3: If the claim is marked as Not OK , it is sent back to the claims officer and the recommendation is repeated . |
| 20 | The driver confirms delivery. The system updates the tracking status. | 1 | 0.444 | 1 | 0/3 | doc-10.2, sentence 10: The GO confirms the assignment to the MPON . |
| 89 | The student submits the assignment. The teacher grades the work. | 1 | 0.444 | 2 | 0/3 | doc-10.2, sentence 10: The GO confirms the assignment to the MPON . |
| 105 | The customer places the order. The kitchen receives the ticket. | 1 | 0.444 | 1 | 0/3 | doc-10.5, sentence 2: The MPON places an order at the MPOO . |
| 173 | The client approves the quote. The agency sends the contract. | 1 | 0.435 | 2 | 0/3 | doc-10.5, sentence 3: The MPOO confirms the order of the MPON and sends the master data . |
| 13 | While the payment is processing, the system displays a loading spinner. | 1 | 0.421 | 3 | 0/4 | doc-5.4, sentence 14: After the payment is confirmed , the process ends . |
| 118 | The user confirms the email address. The system unlocks the features. | 1 | 0.421 | 2 | 0/4 | doc-10.2, sentence 10: The GO confirms the assignment to the MPON . |
| 155 | The server receives the request. The load balancer distributes the traffic. | 1 | 0.421 | 2 | 0/4 | doc-10.13, sentence 1: The IP checks the request of the INQ . |
| 7 | If the claim amount is under $500, process it immediately. Else, require supervisor approval. | 3 | 0.417 | 3 | 0/7 | doc-3.3, sentence 4: If the claim is OK , the claim handling process proceeds . |
| 63 | If the request is from an external IP, block the port. Else, allow the connection. | 3 | 0.417 | 4 | 0/8 | doc-5.3, sentence 3: If the request is rejected the process will end . |
| 69 | If the visa is approved, stamp the passport. If rejected, issue a formal notice. | 3 | 0.417 | 2 | 0/7 | doc-8.2, sentence 6: If the description is finally approved , I post the job . |

## Candidate pairs

| level | pairs |
|---|---|
| a PET relation (any type) joins two mentions with the pair's texts | 0 |
| both entities are mentions of one PET document | 0 |
| both entities occur in one PET sentence | 0 |

Each entity on its own: of the 469 distinct entity texts, 5 are the text of a PET mention ('if', 'in case', 'in case of', 'otherwise', 'should'; one side of 65 pairs), and 9 occur in a PET sentence ('if', 'if not', 'in case', 'in case of', 'otherwise', 'receives the request', 'request changes', 'should', 'when').
