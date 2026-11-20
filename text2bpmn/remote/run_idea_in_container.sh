#!/usr/bin/env bash
# Inside the GPU container: one relation idea (text2bpmn/relation_ideas.py),
# against the vLLM server the final runs used.
#
#     CUDA_VISIBLE_DEVICES= IDEA=1 MODEL=Qwen/Qwen3.5-27B-FP8 API=http://localhost:11434/v1 \
#         nohup ./run_idea_in_container.sh > idea1.log 2>&1 &
#     IDEA=1 ./run_idea_in_container.sh --only pet_decisions      # one experiment again
#
# Run from final_bundle/ after run_in_container.sh has run there once: it reuses
# that script's venv (.venv-final) and checkout (text2bpmn-final), which it
# moves to the tag relation-idea-$IDEA from ideas.bundle; the checkout's runs/
# are git-ignored and stay. DRY_ONLY=1 stops after the dry run. Packs
# idea$IDEA_results.tar.gz.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
REPO=${REPO:-$B/text2bpmn-final}
VENV=${VENV:-$B/.venv-final}
MODEL=${MODEL:-qwen3}
API=${API:-http://localhost:8000/v1}
KEY=${KEY:-EMPTY}
IDEA=${IDEA:?set IDEA, for example IDEA=1}
TAG=relation-idea-$IDEA

[ -f "$VENV/.installed" ] && [ -d "$REPO/.git" ] || {
    echo "run ./run_in_container.sh here once first: it builds $VENV and $REPO"; exit 1; }

echo "== code at $TAG"
git -C "$REPO" fetch -q "$B/ideas.bundle" "+refs/tags/*:refs/tags/*"
git -C "$REPO" checkout -q "$TAG"
git -C "$REPO" describe --tags --exact-match

echo "== files git does not carry"
NER="$REPO/process-visualizer/src/token_classification_alex/bert_ner_315_dev60"
mkdir -p "$NER" "$REPO/text2bpmn/checks/shacl"
cp "$B"/models/bert_ner_315_dev60/* "$NER/"
cp "$B"/models/bert-relation-classifier/* "$REPO/bert-relation-classifier/"
cp "$B/bbo/BPMNbasedOntologyV1_2.owl" "$REPO/"
cp "$B/bbo/SHACLshapes.ttl" "$B/bbo/LICENSE-BBO" "$REPO/text2bpmn/checks/shacl/"
export HF_HOME="$B/hf" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1

cd "$REPO"
"$VENV/bin/python" -c "import fastcoref" || { echo "FastCoref does not import in $VENV"; exit 1; }
"$VENV/bin/python" -m text2bpmn.checks.fetch_bbo
if [ -n "$(git status --porcelain)" ]; then
    echo "the checkout is not clean, and relation_ideas would refuse it:"; git status --short; exit 1
fi

echo "== dry run, no LLM"
"$VENV/bin/python" -m text2bpmn.relation_ideas --idea "$IDEA" --dry-run
[ "${DRY_ONLY:-0}" = 1 ] && { echo "dry run done (DRY_ONLY=1)"; exit 0; }

echo "== checking vLLM at $API for $MODEL"
"$VENV/bin/python" -m text2bpmn.remote.check_server --api-base "$API" --model "$MODEL" --api-key "$KEY" \
    --decisions

echo "== relation idea $IDEA"
status=0
"$VENV/bin/python" -m text2bpmn.relation_ideas --idea "$IDEA" --model "hosted_vllm/$MODEL" --api-base "$API" \
    --api-key "$KEY" --no-thinking --constrained-output --max-tokens 1024 "$@" || status=$?

echo "== packing results"
tar czf "$B/idea${IDEA}_results.tar.gz" "runs/ideas/idea$IDEA" "runs/ideas_dryrun/idea$IDEA"
echo "bring back $B/idea${IDEA}_results.tar.gz (relation_ideas exit status $status)"
exit "$status"
