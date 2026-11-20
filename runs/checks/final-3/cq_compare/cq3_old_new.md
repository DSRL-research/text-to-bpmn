# CQ3 before and after

Old: `runs/checks/final-3/cq_compare/cq_compare.json` at 3a0aad3 (run at revision-final-3-17-ge3ebf32); new: the same file, run at revision-final-3-31-g3a0aad3.

| case | source | old answer | new answer | dropped | added | old cell | new cell |
|---|---|---|---|---|---|---|---|
| loan | reference | 4: {Appraise property, Assess loan risk}; {Appraise property, Check credit history}; {Prepare acceptance pack, Reject application}; {Reject application, Send acceptance pack} | 2: {Appraise property, Assess loan risk}; {Appraise property, Check credit history} | {Prepare acceptance pack, Reject application}; {Reject application, Send acceptance pack} | - |  |  |
| loan | runs/final-3/cases | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) |
| loan | runs/final-3/cases_no_llm | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) |
| loan | runs/gliner-3/cases_gliner | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) |
| loan | runs/gliner-3/cases_gliner_no_llm | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/2/0 (P -, R 0.00) |
| goods_dispatch | reference | 5: {Clarify shipment method, Package goods}; {Get 3 offers from logistic companies, Package goods}; {Insure parcel, Package goods}; {Package goods, Select logistic company and place order}; {Package goods, Write package label} | 5: {Clarify shipment method, Package goods}; {Get 3 offers from logistic companies, Package goods}; {Insure parcel, Package goods}; {Package goods, Select logistic company and place order}; {Package goods, Write package label} | - | - |  |  |
| goods_dispatch | runs/final-3/cases | 1: {Taken a parcel insurance, Written a package label} | 1: {Taken a parcel insurance, Written a package label} | - | - | 0/5/1 (P 0.00, R 0.00) | 0/5/1 (P 0.00, R 0.00) |
| goods_dispatch | runs/final-3/cases_no_llm | 0: - | 0: - | - | - | 0/5/0 (P -, R 0.00) | 0/5/0 (P -, R 0.00) |
| goods_dispatch | runs/gliner-3/cases_gliner | 0: - | 0: - | - | - | 0/5/0 (P -, R 0.00) | 0/5/0 (P -, R 0.00) |
| goods_dispatch | runs/gliner-3/cases_gliner_no_llm | 0: - | 0: - | - | - | 0/5/0 (P -, R 0.00) | 0/5/0 (P -, R 0.00) |
| healthcare | reference | 4: {Complete Treatment, Maintain Communication}; {Interventional Treatment, Maintain Communication}; {Maintain Communication, Medical Treatment}; {Maintain Communication, Surgical Treatment} | 4: {Complete Treatment, Maintain Communication}; {Interventional Treatment, Maintain Communication}; {Maintain Communication, Medical Treatment}; {Maintain Communication, Surgical Treatment} | - | - |  |  |
| healthcare | runs/final-3/cases | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) |
| healthcare | runs/final-3/cases_no_llm | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) |
| healthcare | runs/gliner-3/cases_gliner | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) |
| healthcare | runs/gliner-3/cases_gliner_no_llm | 0: - | 0: - | - | - | 0/4/0 (P -, R 0.00) | 0/4/0 (P -, R 0.00) |
