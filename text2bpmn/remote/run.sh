#!/usr/bin/env bash
# Score the PET flow jobs on this machine. Run it from the bundle root.
#
#     ./remote/run.sh --model ollama/NAME [--documents N] [any finder3 option]
#
# Against an Ollama server, whose model must be named: the pipeline's default
# LLM is now the vLLM-served Qwen/Qwen3.5-27B-FP8, for which
# remote/run_vllm.sh is the runner. Until 2026-11-17 this script ran the
# default ollama/deepseek-10k:latest when --model was left out.
#
# Resumable: every document's result is appended to records.jsonl as it
# finishes, and re-running skips what is already there. Kill it and restart it
# freely.
set -euo pipefail
cd "$(dirname "$0")/.."

case " $* " in
    *" --model ollama/"*) ;;
    *) echo "usage: ./remote/run.sh --model ollama/NAME [options]  (vLLM: remote/run_vllm.sh)" >&2; exit 2 ;;
esac

VENV=${VENV:-.venv-remote}
API=${OLLAMA_API:-http://localhost:11434}

# the stamp is written only after the whole install succeeds; without it an
# interrupted first run leaves a directory that looks finished and fails later
# with a missing import instead of a failed install
if [ ! -f "$VENV/.installed" ]; then
    echo "== creating $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r remote/requirements.txt
    "$VENV/bin/python" -m spacy download en_core_web_sm
    touch "$VENV/.installed"
    echo "== environment ready"
fi
PY="$VENV/bin/python"

echo "== checking the LLM"
if ! curl -sf --max-time 10 "$API/api/tags" >/dev/null; then
    echo "   no Ollama at $API. Start it ('ollama serve'), or set OLLAMA_API." >&2
    exit 1
fi
"$PY" - "$API" <<'PYEOF'
import json, sys, urllib.request
with urllib.request.urlopen(f"{sys.argv[1]}/api/tags", timeout=10) as r:
    models = json.load(r).get("models", [])
print("   models available:", ", ".join(m["name"] for m in models) or "(none)")
PYEOF

echo "== scoring"
exec "$PY" -m text2bpmn.pet_flow_eval \
    --jobs pet_jobs.json \
    --records records.jsonl \
    --json results.json \
    --markdown results.md \
    --api-base "$API" \
    "$@"
