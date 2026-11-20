#!/usr/bin/env bash
# Inside the GPU container: set up the tagged code and run every final
# experiment against the vLLM server running in the same container.
#
#     ./run_in_container.sh [run_final options]
#
# Run from the unpacked final_bundle/. Environment:
#   MODEL       the model id vLLM serves (default qwen3); the run record names
#               it, so serving under the full id (Qwen/Qwen3-8B) is clearer
#   API         vLLM's address (default http://localhost:8000/v1)
#   KEY         its API key (default EMPTY; vLLM ignores it unless started with one)
#   PYTHON      the interpreter for the pipeline's venv (default python3; 3.11 or 3.12)
#   DRY_ONLY=1  stop after the dry run
#
# Run it with CUDA_VISIBLE_DEVICES= in front when vLLM fills the GPU: the
# recogniser and FastCoref then run on the CPU, which is what the laptop's
# dry runs did.
#
# The steps: check the bundle's checksums; clone the code and check out
# revision-final; put the files git does not carry where the pipeline looks;
# build a venv; check that FastCoref imports (the pipeline otherwise carries on
# without it); verify BBO and that the checkout is clean; run the dry run; check
# that vLLM serves MODEL, honours the answer schema and its length limit, and
# keeps thinking off; run the final experiments with thinking off, answers
# constrained by schema (one call per pair) and at most 1024 tokens per reply;
# pack the results and the venv's package list into final_results.tar.gz.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
REPO=${REPO:-$B/text2bpmn-final}
VENV=${VENV:-$B/.venv-final}
MODEL=${MODEL:-qwen3}
API=${API:-http://localhost:8000/v1}
KEY=${KEY:-EMPTY}
PYTHON=${PYTHON:-python3}

echo "== checking the bundle"
(cd "$B" && sha256sum --quiet -c MANIFEST.sha256)

echo "== code at revision-final"
[ -d "$REPO/.git" ] || git clone -q "$B/code.bundle" "$REPO"
git -C "$REPO" checkout -q revision-final
git -C "$REPO" describe --tags --exact-match

echo "== files git does not carry"
NER="$REPO/process-visualizer/src/token_classification_alex/bert_ner_315_dev60"
mkdir -p "$NER" "$REPO/text2bpmn/checks/shacl"
cp "$B"/models/bert_ner_315_dev60/* "$NER/"
cp "$B"/models/bert-relation-classifier/* "$REPO/bert-relation-classifier/"
cp "$B/bbo/BPMNbasedOntologyV1_2.owl" "$REPO/"
cp "$B/bbo/SHACLshapes.ttl" "$B/bbo/LICENSE-BBO" "$REPO/text2bpmn/checks/shacl/"

if [ "${SKIP_INSTALL:-0}" = 1 ]; then
    PY=$PYTHON
else
    if [ ! -f "$VENV/.installed" ]; then
        echo "== creating $VENV"
        "$PYTHON" -m venv "$VENV"
        "$VENV/bin/pip" install -q --upgrade pip
        "$VENV/bin/pip" install -q -r "$B/requirements-final.txt"
        "$VENV/bin/pip" install -q "$B"/wheels/en_core_web_sm-*.whl
        touch "$VENV/.installed"
    fi
    PY="$VENV/bin/python"
fi
export HF_HOME="$B/hf" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1

cd "$REPO"
echo "== FastCoref"
# finder3 catches a coreference failure and carries on with the raw text, so a
# broken install would run every experiment without it (2026-11-04: a pyarrow
# that needed NumPy 2 did exactly that)
"$PY" -c "import fastcoref" || { echo "FastCoref does not import in $PY; fix the venv first"; exit 1; }
"$PY" -m pip freeze > "$B/pip_freeze.txt" 2>/dev/null || true   # outside the checkout, which must stay clean
"$PY" -m text2bpmn.checks.fetch_bbo   # all three present: checks their checksums, downloads nothing
if [ -n "$(git status --porcelain)" ]; then
    echo "the checkout is not clean, and run_final would refuse it:"; git status --short; exit 1
fi

echo "== dry run, no LLM"
"$PY" -m text2bpmn.run_final --dry-run
[ "${DRY_ONLY:-0}" = 1 ] && { echo "dry run done (DRY_ONLY=1)"; exit 0; }

echo "== checking vLLM at $API for $MODEL"
"$PY" -m text2bpmn.remote.check_server --api-base "$API" --model "$MODEL" --api-key "$KEY"

echo "== final runs"
status=0
"$PY" -m text2bpmn.run_final --model "hosted_vllm/$MODEL" --api-base "$API" --api-key "$KEY" \
    --no-thinking --constrained-output --max-tokens 1024 "$@" || status=$?

echo "== packing results"
mkdir -p runs/final && cp "$B/pip_freeze.txt" runs/final/pip_freeze.txt
tar czf "$B/final_results.tar.gz" runs/final runs/dryrun
echo "bring back $B/final_results.tar.gz (run_final exit status $status)"
exit "$status"
