#!/usr/bin/env bash
# Score the PET flow jobs against a vLLM server. Run from the bundle root.
#
#     ./remote/run_vllm.sh MODEL_ID [extra options]
#
# MODEL_ID is what vLLM was started with, e.g. Qwen/Qwen3.5-9B. Everything
# after it is passed through: --constrained-output, --no-thinking, --prompt
# revised, --documents N, --temperature, --seed.
#
# Resumable: each document's record is appended to records_<tag>.jsonl as it
# finishes and a restart skips what is there.
set -euo pipefail
cd "$(dirname "$0")/.."

model=${1:?usage: ./remote/run_vllm.sh MODEL_ID [options]}; shift
API=${VLLM_API:-http://localhost:8000/v1}
KEY=${VLLM_KEY:-EMPTY}
VENV=${VENV:-.venv-remote}
tag=$(echo "$model" | tr '/:' '__')

if [ ! -f "$VENV/.installed" ]; then
    echo "== creating $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r remote/requirements.txt
    "$VENV/bin/python" -m spacy download en_core_web_sm
    touch "$VENV/.installed"
fi
PY="$VENV/bin/python"

echo "== checking vLLM at $API"
"$PY" - "$API" "$KEY" "$model" <<'PYEOF'
import json, sys, urllib.request
api, key, want = sys.argv[1:4]
url = api.rstrip("/") + "/models"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
with urllib.request.urlopen(req, timeout=10) as r:
    served = [m["id"] for m in json.load(r).get("data", [])]
print("   serving:", ", ".join(served) or "(none)")
if want not in served:
    print(f"   WARNING: {want} is not in that list; the run will fail.")
PYEOF

echo "== scoring with $model"
exec "$PY" -m text2bpmn.pet_flow_eval \
    --jobs pet_jobs.json \
    --records "records_$tag.jsonl" \
    --json "results_$tag.json" \
    --markdown "results_$tag.md" \
    --model "hosted_vllm/$model" --api-base "$API" --api-key "$KEY" \
    "$@"
