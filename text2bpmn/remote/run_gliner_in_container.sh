#!/usr/bin/env bash
# Inside the GPU container: the GLiNER arm (text2bpmn/run_gliner_arm.py), the
# pipeline with the fine-tuned GLiNER as its recogniser, against the vLLM
# server the final runs used.
#
#     CUDA_VISIBLE_DEVICES= MODEL=Qwen/Qwen3.5-27B-FP8 API=http://localhost:11434/v1 \
#         nohup ./run_gliner_in_container.sh > gliner.log 2>&1 &
#     ./run_gliner_in_container.sh --only cases_gliner      # one experiment again
#
# Run from final_bundle/ after run_in_container.sh has run there once: it reuses
# that script's venv (.venv-final) and checkout (text2bpmn-final), which it
# moves to the tag revision-final-gliner. GLiNER gets a venv of its own
# (.venv-gliner, from requirements-gliner.txt): it needs a newer transformers
# than DSPy and FastCoref. Environment as for run_in_container.sh, plus
# GVENV (default final_bundle/.venv-gliner) and DRY_ONLY=1 to stop after the
# dry run. Packs gliner_results.tar.gz, with both venvs' package lists.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
REPO=${REPO:-$B/text2bpmn-final}
VENV=${VENV:-$B/.venv-final}
GVENV=${GVENV:-$B/.venv-gliner}
MODEL=${MODEL:-qwen3}
API=${API:-http://localhost:8000/v1}
KEY=${KEY:-EMPTY}
PYTHON=${PYTHON:-python3}
TAG=revision-final-gliner

echo "== checking the bundle"
(cd "$B" && sha256sum --quiet -c MANIFEST.sha256)
[ -f "$VENV/.installed" ] && [ -d "$REPO/.git" ] || {
    echo "run ./run_in_container.sh here once first: it builds $VENV and $REPO"; exit 1; }

echo "== code at $TAG"
git -C "$REPO" fetch -q "$B/code.bundle" "+refs/tags/*:refs/tags/*"
git -C "$REPO" checkout -q "$TAG"
git -C "$REPO" describe --tags --exact-match

echo "== files git does not carry"
NER="$REPO/process-visualizer/src/token_classification_alex/bert_ner_315_dev60"
GLINER="$REPO/text2bpmn/baselines/finetuned_315/A-small-v2.1-315/best"
mkdir -p "$NER" "$GLINER" "$REPO/text2bpmn/checks/shacl"
cp "$B"/models/bert_ner_315_dev60/* "$NER/"
cp "$B"/models/gliner_A-small-v2.1-315/* "$GLINER/"
cp "$B"/models/bert-relation-classifier/* "$REPO/bert-relation-classifier/"
cp "$B/bbo/BPMNbasedOntologyV1_2.owl" "$REPO/"
cp "$B/bbo/SHACLshapes.ttl" "$B/bbo/LICENSE-BBO" "$REPO/text2bpmn/checks/shacl/"

if [ ! -f "$GVENV/.installed" ]; then
    echo "== creating $GVENV"
    "$PYTHON" -m venv "$GVENV"
    "$GVENV/bin/pip" install -q --upgrade pip
    "$GVENV/bin/pip" install -q -r "$B/requirements-gliner.txt"
    touch "$GVENV/.installed"
fi
export HF_HOME="$B/hf" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1
export GLINER_PYTHON="$GVENV/bin/python"

cd "$REPO"
echo "== GLiNER and FastCoref"
"$GLINER_PYTHON" -c "import gliner" || { echo "gliner does not import in $GLINER_PYTHON"; exit 1; }
"$VENV/bin/python" -c "import fastcoref" || { echo "FastCoref does not import in $VENV"; exit 1; }
"$VENV/bin/python" -m pip freeze > "$B/pip_freeze.txt" 2>/dev/null || true
"$GLINER_PYTHON" -m pip freeze > "$B/pip_freeze_gliner.txt" 2>/dev/null || true
"$VENV/bin/python" -m text2bpmn.checks.fetch_bbo
if [ -n "$(git status --porcelain)" ]; then
    echo "the checkout is not clean, and run_gliner_arm would refuse it:"; git status --short; exit 1
fi

echo "== dry run, no LLM"
"$VENV/bin/python" -m text2bpmn.run_gliner_arm --dry-run
[ "${DRY_ONLY:-0}" = 1 ] && { echo "dry run done (DRY_ONLY=1)"; exit 0; }

echo "== checking vLLM at $API for $MODEL"
"$VENV/bin/python" -m text2bpmn.remote.check_server --api-base "$API" --model "$MODEL" --api-key "$KEY"

echo "== GLiNER arm"
status=0
"$VENV/bin/python" -m text2bpmn.run_gliner_arm --model "hosted_vllm/$MODEL" --api-base "$API" --api-key "$KEY" \
    --no-thinking --constrained-output --max-tokens 1024 "$@" || status=$?

echo "== packing results"
mkdir -p runs/gliner && cp "$B/pip_freeze.txt" "$B/pip_freeze_gliner.txt" runs/gliner/
tar czf "$B/gliner_results.tar.gz" runs/gliner runs/gliner_dryrun
echo "bring back $B/gliner_results.tar.gz (run_gliner_arm exit status $status)"
exit "$status"
