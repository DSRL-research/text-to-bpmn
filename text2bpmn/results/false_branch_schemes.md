# The 302-pair benchmarks under both FALSE_BRANCH labelling schemes

Runs in `runs/final`, rescored by `text2bpmn/rescore_false_branch_schemes.py`. **dataset**: the labels of `benchmark_silver_2.jsonl`. **syntactic**: the 23 FALSE_BRANCH pairs without an else-marker relabelled TRUE_BRANCH, the branch taken when the stated condition holds. No model is run again.

| run | dataset labels | syntactic scheme | errors (dataset) | errors (syntactic) | answers on the 23 relabelled pairs |
|---|---|---|---|---|---|
| table3_302 | 278/302 (92.1%) | 295/302 (97.7%) | FALSE_BRANCH->TRUE_BRANCH 20, SEQUENCE->PARALLEL 4 | SEQUENCE->PARALLEL 4, TRUE_BRANCH->FALSE_BRANCH 3 | TRUE_BRANCH 20, FALSE_BRANCH 3 |
| corrected_302 | 278/302 (92.1%) | 297/302 (98.3%) | FALSE_BRANCH->TRUE_BRANCH 21, SEQUENCE->PARALLEL 3 | SEQUENCE->PARALLEL 3, TRUE_BRANCH->FALSE_BRANCH 2 | TRUE_BRANCH 21, FALSE_BRANCH 2 |

Relabelled pairs (line index in `benchmark_silver_2.jsonl`, from 0): 23, 38, 42, 64, 75, 100, 108, 113, 133, 146, 185, 193, 202, 210, 227, 236, 243, 253, 260, 270, 278, 288, 296.
