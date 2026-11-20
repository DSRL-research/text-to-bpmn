#!/usr/bin/env bash
# One process description, every stage of the pipeline, in one call.
#
#     text2bpmn/demo.sh DESCRIPTION.txt [OUTPUT_DIR] [REFERENCE.bpmn]
#
# Run from the repository root; paths inside the pipeline are relative to it.
# Needs the entity recogniser (bert_ner_315_dev60) and the LLM: by default
# Qwen/Qwen3.5-27B-FP8 served by vLLM at http://localhost:11434/v1 (README.md,
# "Serving the LLM"), asked as the final runs asked it (LLM_FLAGS below). Set
# API_BASE for another address, or pass --model/--api-base after the reference
# for another model. Without the LLM the run stops at startup; with
# --allow-no-llm after the reference it goes on, every decision keeps the text
# order and the model comes out sequential, which the extraction JSON records.
#
# Writes, into OUTPUT_DIR (default: a directory named after the input):
#   extraction.json   entities, relations, flows and the run record
#   process.bpmn      BPMN 2.0 XML with a diagram layout
#   process.svg/.png  the drawing
#   process.owl       the BPMN ontology populated from the same structure
#   competency.md     the SPARQL competency questions and their answers
#   comparison.md     against REFERENCE.bpmn, when one is given
set -euo pipefail

input=${1:?usage: text2bpmn/demo.sh DESCRIPTION.txt [OUTPUT_DIR] [REFERENCE.bpmn]}
out=${2:-$(basename "${input%.*}")_run}
reference=${3:-}
python=${PYTHON:-python3}
api_base=${API_BASE:-http://localhost:11434/v1}
# the final method's LLM settings (runs/final-3/*/run_record.json)
read -r -a llm_flags <<< "${LLM_FLAGS:---no-thinking --constrained-output --max-tokens 1024}"

mkdir -p "$out"
name=$(basename "${input%.*}")

echo "== 0. what this run will use"
if curl -sf --max-time 5 "$api_base/models" >/dev/null; then
    echo "   an OpenAI-compatible server answers at $api_base; the LLM will be asked"
else
    echo "   WARNING: no OpenAI-compatible server at $api_base (vllm serve, README.md)."
    echo "   The run stops at startup unless --allow-no-llm is passed after the reference."
fi

echo "== 1. description -> extraction, BPMN and drawing"
$python -m text2bpmn.finder3 "$input" \
    -o "$out/extraction.json" --bpmn "$out/process.bpmn" --svg "$out/process.svg" \
    --seed 0 --temperature 0.0 --api-base "$api_base" "${llm_flags[@]}" "${@:4}"

echo "== 2. PNG of the same diagram"
$python -m text2bpmn.render "$out/process.bpmn" -o "$out/process.svg" --png "$out/process.png" \
    || echo "   (PNG needs inkscape or ImageMagick; the SVG is written either way)"

echo "== 3. populate the BPMN ontology from the same extraction"
$python -m text2bpmn.ontology "$out/extraction.json" -o "$out/process.owl"

echo "== 4. ask the ontology the competency questions"
$python -m text2bpmn.competency "$out/process.owl" --out "$out/competency.md"

if [ -n "$reference" ]; then
    echo "== 5. against the reference model"
    {
        $python -m text2bpmn.compare   --reference "$reference" --generated "$out/process.bpmn"
        $python -m text2bpmn.labels    --reference "$reference" --generated "$out/process.bpmn"
        $python -m text2bpmn.behaviour --reference "$reference" --generated "$out/process.bpmn"
    } | tee "$out/comparison.md"
fi

echo
echo "Wrote $out/:"
ls -1sh "$out"
