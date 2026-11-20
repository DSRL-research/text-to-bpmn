#!/bin/bash
# Fine-tune each configuration in turn. One at a time: each run already uses
# every core, so running them together would only make each slower.
cd "$(dirname "$0")/../.." || exit 1
PY=$HOME/.venvs/gliner-env/bin/python
LOG=text2bpmn/baselines/finetuned
run () { # name, base, extra flags
  echo "=== $1 started $(date -Is)" | tee "$LOG/$1.log"
  timeout 14400 $PY -m text2bpmn.gliner_finetune --base "$2" --name "$1" \
      --train pet_train.json --dev text2bpmn/baselines/dev_split.json \
      --out "$LOG" --epochs 12 --patience 3 ${@:3} >>"$LOG/$1.log" 2>&1
  echo "=== $1 exit $? at $(date -Is)" >>"$LOG/$1.log"
}
run A-small-v2.1   urchade/gliner_small-v2.1
run C-small-focal  urchade/gliner_small-v2.1 --focal 0.75 2
run D-small-hardneg urchade/gliner_small-v2.1 --hard-negatives
run B-medium-v2.1  urchade/gliner_medium-v2.1
