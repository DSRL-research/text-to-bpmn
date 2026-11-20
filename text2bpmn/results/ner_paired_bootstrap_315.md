# Paired bootstrap, micro F1 on pet_test.json

First minus second, both rescored on the same 1000 resamples of the 42 sentences (seed 0); 95% percentile interval; labels: Activity, Activity Data, Actor, AND Gateway, Condition Specification, Further Specification, XOR Gateway. GLiNER thresholds chosen on dev: 0.85 (315), 0.9 (375). Written by text2bpmn/baselines/paired_bootstrap_315.py from saved spans.

| first | second | strict difference [95% CI] | resamples favouring first | relaxed difference [95% CI] | resamples favouring first |
|---|---|---|---|---|---|
| GLiNER A (315) | BERT (315) | +0.134 [+0.085, +0.184] | 1000 | +0.083 [+0.038, +0.127] | 1000 |
| BERT (315) | BERT checkpoint-564 (375) | -0.034 [-0.080, +0.010] | 60 | -0.037 [-0.083, +0.007] | 56 |
| GLiNER A (315) | GLiNER A (375) | -0.002 [-0.023, +0.018] | 398 | -0.008 [-0.032, +0.014] | 260 |
| GLiNER A (375) | BERT checkpoint-564 (375) | +0.102 [+0.036, +0.168] | 1000 | +0.054 [+0.014, +0.095] | 995 |

The last row is the October comparison (both models trained on all 375 sentences; checkpoint-564 selected on this split), kept to check the procedure.
