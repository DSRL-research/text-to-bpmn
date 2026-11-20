#!/usr/bin/env bash
# Inside the GPU container: the method's final runs at the tag revision-final-3
# (text2bpmn/run_final.py, then text2bpmn/run_gliner_arm.py), against the vLLM
# server the earlier runs used.
#
#     CUDA_VISIBLE_DEVICES= MODEL=Qwen/Qwen3.5-27B-FP8 API=http://localhost:11434/v1 \
#         nohup ./run_release_in_container.sh > release.log 2>&1 &
#
# Run from final_bundle/ after run_in_container.sh and run_gliner_in_container.sh
# have run there once: it reuses their venvs (.venv-final, .venv-gliner) and
# checkout (text2bpmn-final), which it moves to revision-final-3 from
# release.bundle; the checkout's earlier runs/ stay. DRY_ONLY=1 stops after the
# dry runs. Packs final3_results.tar.gz, with both venvs' package lists.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
REPO=${REPO:-$B/text2bpmn-final}
VENV=${VENV:-$B/.venv-final}
GVENV=${GVENV:-$B/.venv-gliner}
MODEL=${MODEL:-qwen3}
API=${API:-http://localhost:8000/v1}
KEY=${KEY:-EMPTY}
TAG=revision-final-3

[ -f "$VENV/.installed" ] && [ -f "$GVENV/.installed" ] && [ -d "$REPO/.git" ] || {
    echo "run ./run_in_container.sh and ./run_gliner_in_container.sh here once first"; exit 1; }

echo "== code at $TAG"
git -C "$REPO" fetch -q "$B/release.bundle" "+refs/tags/*:refs/tags/*"
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
    echo "the checkout is not clean, and the final runs would refuse it:"; git status --short; exit 1
fi

echo "== dry runs, no LLM"
"$VENV/bin/python" -m text2bpmn.run_final --dry-run
"$VENV/bin/python" -m text2bpmn.run_gliner_arm --dry-run
[ "${DRY_ONLY:-0}" = 1 ] && { echo "dry runs done (DRY_ONLY=1)"; exit 0; }

echo "== checking vLLM at $API for $MODEL"
"$VENV/bin/python" -m text2bpmn.remote.check_server --api-base "$API" --model "$MODEL" --api-key "$KEY"

LLM=(--model "hosted_vllm/$MODEL" --api-base "$API" --api-key "$KEY" --no-thinking --constrained-output
     --max-tokens 1024)
echo "== final runs"
final=0
"$VENV/bin/python" -m text2bpmn.run_final "${LLM[@]}" || final=$?
echo "== GLiNER arm"
gliner=0
"$VENV/bin/python" -m text2bpmn.run_gliner_arm "${LLM[@]}" || gliner=$?

echo "== packing results"
mkdir -p runs/final-3 && cp "$B/pip_freeze.txt" "$B/pip_freeze_gliner.txt" runs/final-3/
tar czf "$B/final3_results.tar.gz" runs/final-3 runs/gliner-3 runs/dryrun runs/gliner_dryrun
echo "bring back $B/final3_results.tar.gz (run_final exit status $final, run_gliner_arm exit status $gliner)"
[ "$final" = 0 ] && [ "$gliner" = 0 ]
