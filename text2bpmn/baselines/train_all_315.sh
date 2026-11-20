#!/bin/bash
# train_all.sh's four GLiNER configurations, retrained on the 315-sentence pool
# (text2bpmn/clean_split.py) instead of all 375 sentences of pet_train.json, so
# the 60 development sentences their epoch and threshold are chosen on are not
# also trained on. Everything else as in train_all.sh. The 375-sentence models
# stay in finetuned/; these go to finetuned_315/, names ending in -315.
# Then: text2bpmn/baselines/evaluate_finetuned.sh text2bpmn/baselines/finetuned_315/*-315
cd "$(dirname "$0")/../.." || exit 1
PY=$HOME/.venvs/gliner-env/bin/python
LOG=text2bpmn/baselines/finetuned_315
mkdir -p "$LOG"
run () { # name, base, extra flags
  echo "=== $1 started $(date -Is)" | tee "$LOG/$1.log"
  CUDA_VISIBLE_DEVICES= timeout 14400 $PY -m text2bpmn.gliner_finetune --base "$2" --name "$1" \
      --train text2bpmn/baselines/train_315.json --dev text2bpmn/baselines/dev_split.json \
      --out "$LOG" --epochs 12 --patience 3 ${@:3} >>"$LOG/$1.log" 2>&1
  echo "=== $1 exit $? at $(date -Is)" >>"$LOG/$1.log"
}
run A-small-v2.1-315   urchade/gliner_small-v2.1
run C-small-focal-315  urchade/gliner_small-v2.1 --focal 0.75 2
run D-small-hardneg-315 urchade/gliner_small-v2.1 --hard-negatives
run B-medium-v2.1-315  urchade/gliner_medium-v2.1
