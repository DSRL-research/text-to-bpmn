#!/bin/bash
# For each fine-tuned configuration: choose its inference threshold on dev, then
# make exactly one pass over the held-out split and score it.
cd "$(dirname "$0")/../.." || exit 1
PY=$HOME/.venvs/gliner-env/bin/python
B=text2bpmn/baselines
for dir in "$@"; do
  name=$(basename "$dir")
  best="$dir/best"
  [ -d "$best" ] || { echo "skip $name: no best model"; continue; }
  echo "=== $name"
  # dev, for the threshold only
  $PY -m text2bpmn.gliner_baseline --model "$best" --api gliner --phrasing identity \
      --data $B/dev_split.json --out "$B/dev_ft_$name.json" >/dev/null 2>&1
  python3 -m text2bpmn.gliner_baseline --data $B/dev_split.json \
      --sweep "$B/dev_ft_$name.json" --out "$B/sweep_ft_$name.json" 2>/dev/null | tail -1
  # the held-out split, once
  $PY -m text2bpmn.gliner_baseline --model "$best" --api gliner --phrasing identity \
      --data pet_test.json --out "$B/TEST_ft_$name.json" >/dev/null 2>&1
  echo "   test spans written: $B/TEST_ft_$name.json"
done
