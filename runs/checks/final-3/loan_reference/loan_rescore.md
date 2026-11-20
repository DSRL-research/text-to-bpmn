# Loan: the release runs' models against the textbook reference (D12)

Run 2026-11-20T09:01:44+00:00 at revision-final-3-77-g59c3e2b (59c3e2b, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.6.0, pyshacl 0.40.2, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.

Each saved model.bpmn scored with text2bpmn.compare.compare (as run_final.py) and text2bpmn.behaviour.compare_behaviour, against the authored reference the release runs used (`old`; the counts and GED are the run's saved score -- comparison_authored.json where the folder has one, else comparison.json -- and the footprint is computed here) and against the textbook's Solution 3.2 (`new`). RGED = GED / (|G1| + |G2|) (compare.py `rged_combined`), Sim = 1 - RGED (`similarity_combined`); the Eq. 12 values over max(|G1|, |G2|) are in the last two columns. Footprint = behavioural similarity of the relabelled footprints (behaviour.py).

## References

| reference | file | nodes | flows | \|G\| | tasks | task edges | gateways (kind role: n) |
|---|---|---|---|---|---|---|---|
| authored | `text2bpmn/cases/loan/reference_authored.bpmn` | 13 | 14 | 27 | 7 | 7 | AND join: 1, AND split: 1, XOR join: 1, XOR split: 1 |
| textbook | `text2bpmn/cases/loan/reference.bpmn` | 13 | 13 | 26 | 7 | 6 | AND join: 1, AND split: 1, XOR split: 1 |

## Scores

| configuration | ref | tasks TP/FP/FN | P | R | F1 | gateways TP/FP/FN | P | R | F1 | flows TP/FP/FN | P | R | F1 | GED | \|G\| gen | \|G\| ref | RGED | Sim | footprint | RGED max | Sim max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BERT, LLM | old | 5/1/2 | 0.833 | 0.714 | 0.769 | 2/0/2 | 1.000 | 0.500 | 0.667 | 1/4/6 | 0.200 | 0.143 | 0.167 | 19.97 | 20 | 27 | 0.425 | 0.575 | 0.056 | 0.74 | 0.26 |
| BERT, LLM | new | 4/2/3 | 0.667 | 0.571 | 0.615 | 1/1/2 | 0.500 | 0.333 | 0.400 | 1/4/5 | 0.200 | 0.167 | 0.182 | 23.49 | 20 | 26 | 0.511 | 0.489 | 0.059 | 0.904 | 0.096 |
| BERT, no LLM | old | 5/1/2 | 0.833 | 0.714 | 0.769 | 0/0/4 | 0.000 | 0.000 | 0.000 | 1/4/6 | 0.200 | 0.143 | 0.167 | 24.97 | 15 | 27 | 0.595 | 0.405 | 0.056 | 0.925 | 0.075 |
| BERT, no LLM | new | 4/2/3 | 0.667 | 0.571 | 0.615 | 0/0/3 | 0.000 | 0.000 | 0.000 | 1/4/5 | 0.200 | 0.167 | 0.182 | 24.49 | 15 | 26 | 0.597 | 0.403 | 0.059 | 0.942 | 0.058 |
| GLiNER, LLM | old | 4/1/3 | 0.800 | 0.571 | 0.667 | 2/0/2 | 1.000 | 0.500 | 0.667 | 2/2/5 | 0.500 | 0.286 | 0.364 | 18.73 | 18 | 27 | 0.416 | 0.584 | 0.125 | 0.694 | 0.306 |
| GLiNER, LLM | new | 3/2/4 | 0.600 | 0.429 | 0.500 | 1/1/2 | 0.500 | 0.333 | 0.400 | 2/2/4 | 0.500 | 0.333 | 0.400 | 21.25 | 18 | 26 | 0.483 | 0.517 | 0.133 | 0.817 | 0.183 |
| GLiNER, no LLM | old | 4/1/3 | 0.800 | 0.571 | 0.667 | 0/0/4 | 0.000 | 0.000 | 0.000 | 1/3/6 | 0.250 | 0.143 | 0.182 | 25.73 | 13 | 27 | 0.643 | 0.357 | 0.059 | 0.953 | 0.047 |
| GLiNER, no LLM | new | 3/2/4 | 0.600 | 0.429 | 0.500 | 0/0/3 | 0.000 | 0.000 | 0.000 | 1/3/5 | 0.250 | 0.167 | 0.200 | 27.25 | 13 | 26 | 0.699 | 0.301 | 0.062 | 1.048 | 0.0 |

The authored reference scored again here gives the run's saved score exactly: BERT, LLM yes (`comparison_authored.json`), BERT, no LLM yes (`comparison_authored.json`), GLiNER, LLM yes (`comparison_authored.json`), GLiNER, no LLM yes (`comparison_authored.json`).
In `runs/final-3/cases/loan`, comparison.json is the textbook score: yes.
In `runs/final-3/cases_no_llm/loan`, comparison.json is the textbook score: yes.
In `runs/gliner-3/cases_gliner/loan`, comparison.json is the textbook score: yes.
In `runs/gliner-3/cases_gliner_no_llm/loan`, comparison.json is the textbook score: yes.

## BERT, LLM: what was matched

Model `runs/final-3/cases/loan/model.bpmn`.

### against the authored reference (old)

Tasks (reference <- generated, similarity): Check credit history <- Check history (0.8); Assess loan risk <- Assess the applicant’s (0.706); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0); Notify application status <- Approved a loan application (0.52).
Reference tasks unmatched: Appraise property, Assess eligibility. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Sent (Assess loan risk, 0.3).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_join: 1 / 1, 1; XOR_split: 1 / 1, 1.
Flows matched (reference edge = generated edge): Check credit history -> Assess loan risk = Check history -> Assess the applicant’s.
Reference flows missed: Prepare acceptance pack -> Notify application status; Appraise property -> Assess eligibility; Assess eligibility -> Prepare acceptance pack; Assess eligibility -> Reject application; Assess loan risk -> Assess eligibility; Reject application -> Notify application status.
Generated flows extra: Assess the applicant’s -> Prepared the acceptance pack; Assess the applicant’s -> Rejected the application; Prepared the acceptance pack -> Sent; Approved a loan application -> Check history.

### against the textbook reference (new)

Tasks (reference <- generated, similarity): Check credit history <- Check history (0.8); Assess loan risk <- Assess the applicant’s (0.706); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0).
Reference tasks unmatched: Appraise property, Assess eligibility, Send acceptance pack. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Approved a loan application (Reject application, 0.651), Sent (Send acceptance pack, 0.333).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_join: 0 / 1, 0; XOR_split: 1 / 1, 1.
Flows matched (reference edge = generated edge): Check credit history -> Assess loan risk = Check history -> Assess the applicant’s.
Reference flows missed: Prepare acceptance pack -> Send acceptance pack; Appraise property -> Assess eligibility; Assess eligibility -> Prepare acceptance pack; Assess eligibility -> Reject application; Assess loan risk -> Assess eligibility.
Generated flows extra: Assess the applicant’s -> Prepared the acceptance pack; Assess the applicant’s -> Rejected the application; Prepared the acceptance pack -> Sent; Approved a loan application -> Check history.

## BERT, no LLM: what was matched

Model `runs/final-3/cases_no_llm/loan/model.bpmn`.

### against the authored reference (old)

Tasks (reference <- generated, similarity): Check credit history <- Check history (0.8); Assess loan risk <- Assess the applicant’s (0.706); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0); Notify application status <- Approved a loan application (0.52).
Reference tasks unmatched: Appraise property, Assess eligibility. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Sent (Assess loan risk, 0.3).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_join: 1 / 0, 0; XOR_split: 1 / 0, 0.
Flows matched (reference edge = generated edge): Check credit history -> Assess loan risk = Check history -> Assess the applicant’s.
Reference flows missed: Prepare acceptance pack -> Notify application status; Appraise property -> Assess eligibility; Assess eligibility -> Prepare acceptance pack; Assess eligibility -> Reject application; Assess loan risk -> Assess eligibility; Reject application -> Notify application status.
Generated flows extra: Approved a loan application -> Check history; Rejected the application -> Prepared the acceptance pack; Assess the applicant’s -> Rejected the application; Prepared the acceptance pack -> Sent.

### against the textbook reference (new)

Tasks (reference <- generated, similarity): Check credit history <- Check history (0.8); Assess loan risk <- Assess the applicant’s (0.706); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0).
Reference tasks unmatched: Appraise property, Assess eligibility, Send acceptance pack. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Approved a loan application (Reject application, 0.651), Sent (Send acceptance pack, 0.333).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_split: 1 / 0, 0.
Flows matched (reference edge = generated edge): Check credit history -> Assess loan risk = Check history -> Assess the applicant’s.
Reference flows missed: Prepare acceptance pack -> Send acceptance pack; Appraise property -> Assess eligibility; Assess eligibility -> Prepare acceptance pack; Assess eligibility -> Reject application; Assess loan risk -> Assess eligibility.
Generated flows extra: Approved a loan application -> Check history; Rejected the application -> Prepared the acceptance pack; Assess the applicant’s -> Rejected the application; Prepared the acceptance pack -> Sent.

## GLiNER, LLM: what was matched

Model `runs/gliner-3/cases_gliner/loan/model.bpmn`.

### against the authored reference (old)

Tasks (reference <- generated, similarity): Assess eligibility <- Assess the applicant’s eligibility (0.75); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0); Notify application status <- Approved a loan application (0.52).
Reference tasks unmatched: Check credit history, Assess loan risk, Appraise property. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Sent (Assess loan risk, 0.3).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_join: 1 / 1, 1; XOR_split: 1 / 1, 1.
Flows matched (reference edge = generated edge): Assess eligibility -> Prepare acceptance pack = Assess the applicant’s eligibility -> Prepared the acceptance pack; Assess eligibility -> Reject application = Assess the applicant’s eligibility -> Rejected the application.
Reference flows missed: Prepare acceptance pack -> Notify application status; Appraise property -> Assess eligibility; Check credit history -> Assess loan risk; Assess loan risk -> Assess eligibility; Reject application -> Notify application status.
Generated flows extra: Prepared the acceptance pack -> Sent; Approved a loan application -> Assess the applicant’s eligibility.

### against the textbook reference (new)

Tasks (reference <- generated, similarity): Assess eligibility <- Assess the applicant’s eligibility (0.75); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0).
Reference tasks unmatched: Check credit history, Assess loan risk, Appraise property, Send acceptance pack. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Approved a loan application (Reject application, 0.651), Sent (Send acceptance pack, 0.333).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_join: 0 / 1, 0; XOR_split: 1 / 1, 1.
Flows matched (reference edge = generated edge): Assess eligibility -> Prepare acceptance pack = Assess the applicant’s eligibility -> Prepared the acceptance pack; Assess eligibility -> Reject application = Assess the applicant’s eligibility -> Rejected the application.
Reference flows missed: Prepare acceptance pack -> Send acceptance pack; Appraise property -> Assess eligibility; Check credit history -> Assess loan risk; Assess loan risk -> Assess eligibility.
Generated flows extra: Prepared the acceptance pack -> Sent; Approved a loan application -> Assess the applicant’s eligibility.

## GLiNER, no LLM: what was matched

Model `runs/gliner-3/cases_gliner_no_llm/loan/model.bpmn`.

### against the authored reference (old)

Tasks (reference <- generated, similarity): Assess eligibility <- Assess the applicant’s eligibility (0.75); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0); Notify application status <- Approved a loan application (0.52).
Reference tasks unmatched: Check credit history, Assess loan risk, Appraise property. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Sent (Assess loan risk, 0.3).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_join: 1 / 0, 0; XOR_split: 1 / 0, 0.
Flows matched (reference edge = generated edge): Assess eligibility -> Reject application = Assess the applicant’s eligibility -> Rejected the application.
Reference flows missed: Prepare acceptance pack -> Notify application status; Appraise property -> Assess eligibility; Check credit history -> Assess loan risk; Assess eligibility -> Prepare acceptance pack; Assess loan risk -> Assess eligibility; Reject application -> Notify application status.
Generated flows extra: Rejected the application -> Prepared the acceptance pack; Approved a loan application -> Assess the applicant’s eligibility; Prepared the acceptance pack -> Sent.

### against the textbook reference (new)

Tasks (reference <- generated, similarity): Assess eligibility <- Assess the applicant’s eligibility (0.75); Reject application <- Rejected the application (1.0); Prepare acceptance pack <- Prepared the acceptance pack (1.0).
Reference tasks unmatched: Check credit history, Assess loan risk, Appraise property, Send acceptance pack. Generated tasks unmatched (closest reference task by compare.similarity, whether or not it is assigned to another task; similarity): Approved a loan application (Reject application, 0.651), Sent (Send acceptance pack, 0.333).
Gateways (kind_role: reference / generated, matched): AND_join: 1 / 0, 0; AND_split: 1 / 0, 0; XOR_split: 1 / 0, 0.
Flows matched (reference edge = generated edge): Assess eligibility -> Reject application = Assess the applicant’s eligibility -> Rejected the application.
Reference flows missed: Prepare acceptance pack -> Send acceptance pack; Appraise property -> Assess eligibility; Check credit history -> Assess loan risk; Assess eligibility -> Prepare acceptance pack; Assess loan risk -> Assess eligibility.
Generated flows extra: Rejected the application -> Prepared the acceptance pack; Approved a loan application -> Assess the applicant’s eligibility; Prepared the acceptance pack -> Sent.
