import argparse
import json
import random
import torch
import dspy
import pandas as pd
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from tqdm import tqdm
import os
from dspy.teleprompt import LabeledFewShot

from text2bpmn.guardrails import false_branch_guardrail
from text2bpmn.relation_parsing import ParseFailureLog
from text2bpmn.run_config import RunConfig, add_arguments, from_arguments

# --- CONFIGURATION ---
BERT_MODEL_PATH = "bert-relation-classifier"

parser = argparse.ArgumentParser(description="Benchmark relation extraction: BERT baseline vs DSPy.")
parser.add_argument("--dataset", default="benchmark_silver_2.jsonl")
parser.add_argument("--few-shot-data", dest="few_shot_data", default="benchmark_unseen.jsonl")
parser.add_argument("--sample-size", dest="sample_size", type=int, default=302)
parser.add_argument("--report", default="text2bpmn/results/benchmark_relations.md")
# seed 51 is what the published run sampled with
add_arguments(parser, RunConfig(seed=51))
args = parser.parse_args()

CONFIG = from_arguments(args)  # also seeds every random source
RUN_RECORD = CONFIG.describe()
CONFIG.require_llm(RUN_RECORD)  # no answers from a cache standing in for a server that is down
TEST_DATASET_PATH, TRAIN_DATASET_PATH = args.dataset, args.few_shot_data
SAMPLE_SIZE, OUTPUT_REPORT = args.sample_size, args.report
PARSE_FAILURES = OUTPUT_REPORT.replace(".md", "_parse_failures.jsonl")
RUN_RECORD_PATH = OUTPUT_REPORT.replace(".md", "_run.json")
print(f"Run config: {json.dumps(RUN_RECORD, indent=2)}")

# --- 1. SETUP MODELS ---

# A. SETUP BERT (Baseline)
print("Loading BERT Baseline Model...")
bert_model = None
bert_tokenizer = None
try:
    bert_tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_PATH)
    bert_model = AutoModelForSequenceClassification.from_pretrained(BERT_MODEL_PATH)
    bert_model.eval()
except Exception as e:
    print(f"Error loading BERT model: {e}")

def predict_bert(text, e1, e2):
    if bert_model is None: return "ERROR"
    # Mimic finder2.py logic
    input_text = f"{e1} : {e2}"
    inputs = bert_tokenizer(
        input_text, 
        text, 
        return_tensors="pt", 
        truncation=True, 
        max_length=128
    )
    
    with torch.no_grad():
        logits = bert_model(**inputs).logits
    
    pred_id = torch.argmax(logits, dim=-1).item()
    prediction = bert_model.config.id2label[pred_id]
    
    # --- SYMBOLIC OVERRIDE (same rule as the DSPy path) ---
    return false_branch_guardrail(prediction, e1, e2, CONFIG.guardrail_mode)

# B. SETUP DSPy (New Approach)
print("Loading DSPy Local Model...")
# The pipeline's own client and adapter: API key, deadline, thinking and
# constrained answers as the run configuration says (it used to hard-code the
# key and ignore the rest, so a vLLM run of this benchmark could not match the
# pipeline's settings). No try/except: a setup failure used to print and exit
# with status 0.
from text2bpmn.finder3 import configure_dspy
configure_dspy(CONFIG)

# The pipeline's own classifier. This script used to keep a copy of the
# signature whose rule 5 had no examples; that copy produced Table 3 and is
# kept as the "table3" prompt in text2bpmn/prompts.py.
from text2bpmn.finder3 import BPMNRelationPredictor
from text2bpmn.prompts import load_demonstrations

# Few-shot demonstrations; a missing or malformed file stops the run
train_examples = load_demonstrations(TRAIN_DATASET_PATH)
print(f"Loaded {len(train_examples)} few-shot examples from {TRAIN_DATASET_PATH}.")

# Compile DSPy Module
print("Compiling DSPy Module...")
uncompiled_predictor = BPMNRelationPredictor(CONFIG.prompt)
teleprompter = LabeledFewShot(k=CONFIG.few_shot_k)
predictor = teleprompter.compile(student=uncompiled_predictor, trainset=train_examples)

relation_log = ParseFailureLog()  # every DSPy call; failures kept with the raw output

def predict_dspy(text, e1, e2):
    try:
        pred = predictor(context=text, node_A=e1, node_B=e2)
        # Return tuple (relation, reasoning)
        # ChainOfThought's field; DSPy 2 called it `rationale`, and reading that
        # name left this column "No reasoning" for every pair
        reasoning = getattr(pred, 'reasoning', None) or "No reasoning"

        # --- DEBUG LOG ---
        try:
            if dspy.settings.lm and hasattr(dspy.settings.lm, 'history') and dspy.settings.lm.history:
                last_interaction = dspy.settings.lm.history[-1]
                print(f"\n[LLM Debug] Relation: {pred.relation}")
                print(f"[LLM Debug] Reasoning: {reasoning}")
                # Safe access to prompt/response keys
                p = last_interaction.get('prompt', '')
                r = last_interaction.get('response', '')
                print(f"[LLM Debug] Raw Prompt Tail: ...{str(p)[-200:]}")
                print(f"[LLM Debug] Raw Response: {r}")
            else:
                print(f"[LLM Debug] History empty or unavailable.")
        except Exception as debug_e:
            print(f"[LLM Debug] Logging Failed: {debug_e}")
        # -----------------
        
        return relation_log.parse(pred.relation, node_A=e1, node_B=e2), reasoning
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return relation_log.error(e, node_A=e1, node_B=e2), str(e)
# --- 2. LOAD & SAMPLE DATA (Test Set) ---
print(f"Loading TEST dataset from {TEST_DATASET_PATH}...")
data = []
if os.path.exists(TEST_DATASET_PATH):
    with open(TEST_DATASET_PATH, 'r') as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line: continue
            if line.endswith(','): line = line[:-1] # Handle potential trailing comma
            if line.endswith('.'): line = line[:-1] # Handle potential trailing period
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                pass
else:
    print(f"Error: Test dataset {TEST_DATASET_PATH} not found.")
    exit()

# Sample Data
actual_sample_size = min(len(data), SAMPLE_SIZE)
random.seed(CONFIG.seed)
test_set = random.sample(data, actual_sample_size)
print(f"Selected {len(test_set)} samples for benchmarking.")

# --- 3. RUN BENCHMARK ---
results = []
correct_bert = 0
correct_dspy = 0

print(f"Running Inference on {len(test_set)} items...")
for item in tqdm(test_set):
    text = item['text']
    e1 = item['entity_1']
    e2 = item['entity_2']
    ground_truth = item['label']
    
    # Run Models
    pred_b = predict_bert(text, e1, e2)
    pred_d_raw, reasoning = predict_dspy(text, e1, e2)
    
    pred_d_clean = pred_d_raw  # already a label or UNKNOWN (ticket C7)

    # --- GUARDRAILS ---
    pred_d_clean = false_branch_guardrail(pred_d_clean, e1, e2, CONFIG.guardrail_mode)

    # Score
    is_bert_correct = (pred_b == ground_truth)
    is_dspy_correct = (pred_d_clean == ground_truth)
    
    if is_bert_correct: correct_bert += 1
    if is_dspy_correct: correct_dspy += 1
    
    results.append({
        "text": text,
        "e1": e1,
        "e2": e2,
        "ground_truth": ground_truth,
        "bert_pred": pred_b,
        "dspy_pred": pred_d_clean,
        "dspy_reasoning": reasoning,
        "bert_correct": is_bert_correct,
        "dspy_correct": is_dspy_correct
    })

# --- 4. GENERATE REPORT ---
acc_bert = (correct_bert / actual_sample_size) * 100
acc_dspy = (correct_dspy / actual_sample_size) * 100

report = f"""# Benchmark Report: BERT vs DSPy (Few-Shot)

**Sample Size**: {actual_sample_size}
**Test Dataset**: {TEST_DATASET_PATH}
**Few-Shot Examples**: {len(train_examples)}
**DSPy parse failures (UNKNOWN)**: {len(relation_log.failures)}/{relation_log.calls}
**Run**: seed {CONFIG.seed}, temperature {CONFIG.temperature}, model {RUN_RECORD['llm']}, code {RUN_RECORD['code']}
**Answers**: {'constrained by schema, one call per pair, reasoning at most ' + str(CONFIG.reasoning_max_chars) + ' characters' if CONFIG.constrained_output else 'free text (ChatAdapter)'}, thinking {'off' if CONFIG.disable_thinking else 'model default'}, max tokens {CONFIG.max_tokens or 'server default'}

## 🏆 Overall Accuracy
| Model | Accuracy | Correct |
| :--- | :--- | :--- |
| **BERT (Baseline)** | **{acc_bert:.1f}%** | {correct_bert}/{actual_sample_size} |
| **DSPy ({CONFIG.llm_model.split('/', 1)[-1]})** | **{acc_dspy:.1f}%** | {correct_dspy}/{actual_sample_size} |

## 🔍 Detailed Errors
Cases where models disagreed or failed.

"""
report += "| Context | Pair | Ground Truth | BERT | DSPy | DSPy Reasoning |\n"
report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"

for res in results:
    if not res['bert_correct'] or not res['dspy_correct']:
        mark_b = "✅" if res['bert_correct'] else "❌"
        mark_d = "✅" if res['dspy_correct'] else "❌"
        ctx = res['text'][:40] + "..." if len(res['text']) > 40 else res['text']
        # Escape pipes in reasoning
        reasoning_clean = res['dspy_reasoning'].replace("|", "/").replace("\n", " ")[:100] + "..."
        report += f"| {ctx} | {res['e1']} -> {res['e2']} | **{res['ground_truth']}** | {mark_b} {res['bert_pred']} | {mark_d} {res['dspy_pred']} | {reasoning_clean} |\n"

with open(OUTPUT_REPORT, "w") as f:
    f.write(report)
with open(RUN_RECORD_PATH, "w") as f:
    json.dump(RUN_RECORD, f, indent=2)
with open(PARSE_FAILURES, "w") as f:
    for record in relation_log.failures:
        f.write(json.dumps(record) + "\n")

print(f"\nBenchmark Complete! Results saved to {OUTPUT_REPORT}")
print(f"BERT Accuracy: {acc_bert:.1f}%")
print(f"DSPy Accuracy: {acc_dspy:.1f}%")
print(f"DSPy parse failures: {len(relation_log.failures)}/{relation_log.calls} (details in {PARSE_FAILURES})")
