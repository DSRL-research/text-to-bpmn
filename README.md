# Text to BPMN

Code, runs and evaluation for the paper "A Multi-Layered AI Pipeline for
Process Model Generation from Text" (Software and Systems Modeling, manuscript
SOSYM-26-00005703).

The pipeline generates BPMN 2.0 process models from natural-language process
descriptions:
1. **Entity recognition.** A fine-tuned token classifier finds the steps,
   actors, decisions and concurrency words.
2. **Ordering and questions to a local LLM.** The steps are put in the order the
   text gives them. Each decision is resolved by one question: which of the
   following steps are done when the condition holds, which when it does not,
   and where the branches meet again (`text2bpmn/decisions.py`). Each
   concurrency word ("in the meantime") gets one more question: which steps
   around it run side by side, and where the lines of work meet.
3. **Validation.** A validation layer turns the result into well-formed control
   flow, and every model is checked for soundness before it is written
   (`text2bpmn/soundness_gate.py`).
4. **Output.** The model is serialised to BPMN 2.0 XML with a diagram layout, and
   the BPMN Based Ontology (BBO) is populated from the same structure.

This repository holds:
- the pipeline;
- the release runs it was evaluated with, and every model they generated;
- the scripts that rebuild every table and figure of the paper from those runs,
  without a GPU or the LLM.

Run records reference commits of the development repository, which is
available from the authors on request. The release runs were made at its tag
`revision-final-3` (commit `808815f805259940897ef6171cc546420a688221`).

## Contents

| Path | What it is |
|---|---|
| `text2bpmn/` | the pipeline (`finder3.py` and the modules it imports), the evaluation scripts (`checks/`, `paper_tables.py`, …), the tests, the case studies (`cases/`), the recognisers' test spans and training records (`baselines/`) and the scripts' results (`results/`) |
| `runs/` | the release runs and the earlier runs that the tables read (each folder has its `run_record.json`); `runs/checks/` holds the checks' and tables' outputs |
| `figures/` | the figures drawn from the runs, and the commands that draw them |
| `benchmark_silver_2.jsonl` | the 302 constructed candidate pairs (Table 6); `prompt_for_llm.md` is the prompt found with the set (see "The 302-pair set" below) |
| `benchmark_unseen.jsonl` | the 10 worked examples of the pairwise classifier's prompt (`text2bpmn/prompts.py`) |
| `pet_data/`, `pet_train.json`, `pet_test.json` | the PET dataset v1.1 and its splits (MIT, `third_party/pet/NOTICE`) |
| `third_party/` | notices for third-party files kept here under their own terms, and the Camunda exercise text |
| `benchmark_results_silver_fewshot_final2.md` | a test fixture: the stored 302-pair run behind the submitted version's Table 3 |

**The 302-pair set.** `benchmark_silver_2.jsonl` holds 302 candidate pairs from
185 fragments. The fragments were generated with Gemini 3 Pro on 30 January
2026 from `prompt_for_llm.md` (authors' record; the raw model output was not
kept, and the hand-written fragments are not marked individually).
`python3 -m text2bpmn.checks.silver_pet_overlap` compares every fragment and
every candidate pair with all 45 PET documents
(`text2bpmn/results/silver_pet_overlap.md`).

## Install

Python 3.12, from the repository root:

```bash
python3.12 -m venv .venv && . .venv/bin/activate
# without a GPU: torch's CPU build of the pinned version first (the default Linux
# wheel brings about 4 GB of CUDA libraries); with a GPU, skip this line
pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m spacy download en_core_web_sm
# BBO, the ontology the pipeline populates, with its SHACL shapes: GPL-3.0, so
# fetched from its repository at a pinned commit and checked, not committed
python3 -m text2bpmn.checks.fetch_bbo
# Neuberger et al.'s PET conversion and stored outputs (Tables 5, 8, 9): fetched, checked
python3 -m text2bpmn.pet_strict --fetch
```

`requirements.txt` pins every package the tables need, including
`transformers==4.50.0`, the version of the release runs. The exact environment
of the release runs is `runs/final-3/pip_freeze.txt` (and
`pip_freeze_gliner.txt` for the GLiNER arm).

## The recogniser weights

The two entity recognisers' weights are not in git. They are deposited on
Zenodo: [10.5281/zenodo.24388158](https://doi.org/10.5281/zenodo.24388158).
Only the generation of new models needs them; the tables are rebuilt from the
committed runs.

**BERT, `bert_ner_315_dev60`, the pipeline's default.** The pipeline expects
it at `process-visualizer/src/token_classification_alex/bert_ner_315_dev60/`
(`NER_MODEL_PATH` in `text2bpmn/finder3.py`; change it to point elsewhere).
- bert-base-cased fine-tuned on 315 sentences of PET's training split by
  `python3 -m text2bpmn.train_ner --out <folder>`, its epoch chosen on the other
  60.
- Training record: `text2bpmn/baselines/bert_ner_315_dev60/train_record.json`.

| File | Bytes | SHA-256 |
|---|---|---|
| `config.json` | 1,476 | `faaec42c9c119575b5c08089609f505c5c17d2fd693e6311833af29679fee6b3` |
| `model.safetensors` | 430,948,196 | `e17e92268b8fae651626b54c8dc89ac2f9add25bdfcc042e7ecddacc371745a7` |
| `special_tokens_map.json` | 125 | `b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3` |
| `tokenizer.json` | 669,021 | `cb26b43c98e8266ae3e99c2a583cf8315d73b33a17e6b20b4df7ff1f22392d34` |
| `tokenizer_config.json` | 1,222 | `1c441dfe412d9d7e47c960029a48a0159c23a38a9ab41b465d90fb1f520d4ced` |
| `trainer_state.json` | 10,140 | `a37bc9f27b754226f8893636ed0890bb40d6b3bb08ff8a992d0a132b82859c22` |
| `training_args.json` | 4,103 | `a0ca05d1d13de35c33f25c33f61b695ff218d42a13bbffa06bc32e8c51e04361` |
| `train_record.json` | 3,057 | `a974d8ad20b07a3dd2cc390c20623e2f4a284c1b486b692fc262bd99ad3d8a9e` |
| `vocab.txt` | 213,450 | `eeaa9875b23b04b4c54ef759d03db9d1ba1554838f8fb26c5d96fa551df93d02` |

**GLiNER configuration A, `A-small-v2.1-315`, the alternative recogniser.**
Expected at `text2bpmn/baselines/finetuned_315/A-small-v2.1-315/best/`.
- `urchade/gliner_small-v2.1` fine-tuned on the same 315 sentences
  (`text2bpmn/baselines/train_all_315.sh`), used at threshold 0.85.
- Training record: `text2bpmn/baselines/finetuned_315/A-small-v2.1-315/run.json`.

| File | Bytes | SHA-256 |
|---|---|---|
| `gliner_config.json` | 2,395 | `24529bb53fe418337d41cfd3ec5ca34a1d7143f47a7f395996c44008176fa2b1` |
| `pytorch_model.bin` | 610,640,099 | `1afa6921385ac326ef0cf3c761345a24f2272b27143b04a4614f32aa9e027dff` |
| `tokenizer.json` | 8,340,684 | `1731c431e5e851a4a73487b5bbfbef265b29ab64de190c402b4e6df9ce2cb0ab` |
| `tokenizer_config.json` | 538 | `0dbe41323167ba5f2e1e876ccd05068318dd2378b922bdfd924a389dba3bcc7a` |

`pytorch_model.bin` is a pickle; load it only from the deposit, after checking
its SHA-256. `training_args.json` is the BERT run's
`TrainingArguments.to_json_string()`. It and the deposited `train_record.json`
have their path fields set to relative values, so that `train_record.json`
differs from the committed copy in those two values.

## Reproducing the paper

Two stages:
1. **Generate the models.** This needs a GPU. Its output is committed under
   `runs/`.
2. **Compute every table and figure from those runs.** This needs neither the
   GPU nor the LLM.

### Every table and figure from the committed runs (CPU)

Run from the repository root, after "Install", in this order:

```bash
# 1. Tables 2-10, each compared with the draft (35 s)
python3 -m text2bpmn.paper_tables all
# 2. the four loan configurations against both loan references (1 s)
python3 -m text2bpmn.checks.loan_rescore
# 3. Tables 11-12, the competency questions: queries, answers, scores, run times (about 1.5 min)
python3 -m text2bpmn.checks.cq_compare runs/final-3/cases runs/final-3/cases_no_llm \
    runs/gliner-3/cases_gliner runs/gliner-3/cases_gliner_no_llm --layout release \
    --out runs/checks/final-3/cq_compare --references runs/checks/final-3/cq_compare/references
# 4. the Section 4.6 drawings, then the check that no line crosses a box (15 s)
sh figures/section_4_6/commands.txt
python3 -m text2bpmn.render_check figures/section_4_6/*.svg --json figures/section_4_6/check.json
# 5. the remaining numbers of Sections 3 and 4 (each a few seconds; see the table below)
python3 -m text2bpmn.checks.pet_counts
python3 -m text2bpmn.ner_comparison --spec text2bpmn/baselines/comparison_spec_315.json \
    --out text2bpmn/results/ner_comparison_315.md --json text2bpmn/results/ner_comparison_315.json
PYTHONPATH=. python3 text2bpmn/baselines/paired_bootstrap_315.py
python3 -m text2bpmn.pet_strict
python3 -m text2bpmn.rescore_false_branch_schemes
python3 -m text2bpmn.compare_gliner_arm --release
python3 -m text2bpmn.checks.method_analysis
python3 -m text2bpmn.checks.token_usage
python3 -m text2bpmn.checks.decision_prompt
python3 -m text2bpmn.checks.concurrency_prompt
python3 -m text2bpmn.checks.kg_fragment
python3 -m text2bpmn.checks.window_coverage
python3 -m text2bpmn.checks.else_marker_decisions
python3 -m text2bpmn.checks.unseen_pronoun_lanes
python3 -m text2bpmn.checks.unmatched_tasks
python3 -m text2bpmn.checks.unmatched_tasks --cases loan --name unmatched_tasks_loan \
    --reference loan=text2bpmn/cases/loan/reference.bpmn
python3 -m text2bpmn.checks.silver_pet_overlap
python3 -m text2bpmn.checks.repeated_runs      # prints only; exits 1 if a repeat differs
python3 -m text2bpmn.checks.table5_sources     # asks GitHub which refs hold the pins (git ls-remote)
# 6. Section 4.5.3, the validity of the models: write the 135 PET models again
#    (byte for byte), then XSD, WOFLAN (about 5 min) and SHACL (26 to 45 min)
for a in pet_decisions pet_no_and pet_no_llm; do
    python3 -m text2bpmn.checks.write_pet_models runs/final-3/$a --out runs/checks/final-3/pet_models/$a
done
M="runs/checks/final-3/pet_models/pet_decisions runs/checks/final-3/pet_models/pet_no_and
   runs/checks/final-3/pet_models/pet_no_llm runs/final-3/cases runs/final-3/cases_no_llm
   runs/final-3/coref_ablation runs/gliner-3/cases_gliner runs/gliner-3/cases_gliner_no_llm
   runs/gliner-3/lanes_gliner"
python3 -m text2bpmn.checks.xsd_validate $M --out runs/checks/final-3/xsd
python3 -m text2bpmn.checks.soundness $M --out runs/checks/final-3/soundness
python3 -m text2bpmn.checks.shacl_validate runs/final-3/cases runs/final-3/cases_no_llm \
    runs/gliner-3/cases_gliner runs/gliner-3/cases_gliner_no_llm \
    runs/final-3/coref_ablation/with_coref runs/final-3/coref_ablation/without_coref \
    runs/gliner-3/lanes_gliner/with_coref runs/final-3/pet_decisions/documents \
    --out runs/checks/final-3/shacl
# 7. Table 8 with WOFLAN run again on all 180 models (about 3 min)
python3 -m text2bpmn.paper_tables 8 --woflan
# 8. the tests (about 1 min)
python3 -m pytest text2bpmn/tests -q
```

Each command writes its results over the committed ones, so `git diff` shows
what changed. Only the header lines should differ: the run time, the commit,
and the package versions. Each report's header also records whether the tree
was clean ("dirty"). An earlier command's rewritten reports make the tree
dirty, so for clean headers run `git checkout -- .` between commands.

Times were measured on a laptop with an Intel Core i7-1355U, 12 threads, 16 GB
of RAM and no GPU.

`paper_tables` rebuilds each table with the scorers the runs used and lays it
out as its draft prints it. It then compares every number in the table, and the
numbers its section's text reports with it, with the draft. It writes
`runs/checks/final-3/tables/table<N>.{md,json}` and `summary.md`, and exits 1
on a difference it cannot explain. Of the 351 values compared, 4 differ; all
four are explained in "Where the drafts differ from the runs".

### The paper, section by section

Section numbers are those of the drafts of November 2026; they may change.

| Paper | What | Command | Reads | Writes |
|---|---|---|---|---|
| §2, Table 1 | the comparison of approaches | none: it compares the literature | – | – |
| §3.1 | training the recognisers | `python3 -m text2bpmn.train_ner --out <folder>` (BERT); `text2bpmn/baselines/train_all_315.sh` (GLiNER, in its own environment, `text2bpmn/remote/requirements-gliner.txt`) | `text2bpmn/baselines/train_315.json`, `dev_split.json` | the weights (see "The recogniser weights") |
| §3.2 | the questions to the LLM, as sent | `python3 -m text2bpmn.checks.decision_prompt` (Section 3.2.4's box, the loan case's second question); `python3 -m text2bpmn.checks.concurrency_prompt` | `runs/final-3/cases` | `runs/checks/final-3/open_analyses/decision_prompt_loan.md`, `concurrency_prompt_goods_dispatch.md` |
| §3.2.3 | the reach of the decision question: PET's Flow relations by distance in mentions | `python3 -m text2bpmn.checks.window_coverage`; the backward flows the method builds: `checks.method_analysis` | `pet_data/PETv1.1-relations.json` | `runs/checks/window/window_coverage.{md,json}` (the JSON has each flow's distance: 626 of 675 within ten mentions, 6 further, 43 backward); `text2bpmn/results/method_analysis.md` |
| §3.2 | the prompts | `INSTRUCTIONS_SAME` and `INSTRUCTIONS_PARALLEL` in `text2bpmn/decisions.py` (the method); the pairwise classifier's in `text2bpmn/prompts.py` with its 10 examples in `benchmark_unseen.jsonl` | – | – |
| §3.3 | one model, with every rule applied | `python3 -m text2bpmn.generate <extraction.json> -o out.bpmn --report rules.json` | a saved extraction, e.g. `runs/final-3/cases/loan/extraction.json` | the BPMN file and the rule log |
| §3.3.6 | a fragment of the loan case's knowledge graph | `python3 -m text2bpmn.checks.kg_fragment` (needs graphviz `dot`) | `runs/final-3/cases/loan/ontology.owl` | `figures/section_3_3_6/loan_kg_fragment.*` |
| §4.1, Table 2 | PET's entity distribution | `python3 -m text2bpmn.paper_tables 2`; beside PET's own paper: `python3 -m text2bpmn.checks.pet_counts` | `pet_data/PETv1.1-relations.json` | `runs/checks/final-3/tables/table2.md`, `runs/checks/pet_counts/` |
| §4.1 | the 302 constructed pairs, and whether any fragment or pair comes from PET | `python3 -m text2bpmn.checks.silver_pet_overlap` | `benchmark_silver_2.jsonl`; all 45 PET documents (`pet_data/`, `pet_train.json`, `pet_test.json`) | `text2bpmn/results/silver_pet_overlap.{md,json}` |
| §4.2, Tables 3-4 | strict F1 per mention type; the recognition configurations with 95% intervals | `python3 -m text2bpmn.paper_tables 3`, `paper_tables 4`; every configuration: the `ner_comparison` command above; the paired differences: `PYTHONPATH=. python3 text2bpmn/baselines/paired_bootstrap_315.py` | the committed test spans of `text2bpmn/baselines/comparison_spec_315.json`; the parameter counts' record `runs/checks/final-3/tables/parameter_counts.json` | `tables/table3.md`, `table4.md`; `text2bpmn/results/ner_comparison_315.md`, `ner_paired_bootstrap_315.md` |
| §4.2 | the cross-validation of the recognisers | `PYTHONPATH=. python3 text2bpmn/baselines/score_cv_protocols.py text2bpmn/baselines/cv/clean_315_2026-11-09/bert-base` (and `…/gliner-small`) | the folds' predictions in `text2bpmn/baselines/cv/clean_315_2026-11-09/`, the folds `text2bpmn/baselines/cv_folds.json` | prints both protocols' tables and writes `text2bpmn/results/cv_protocols_<model>.json`; the committed copies are `cv_protocols_clean_315_<model>.json` (the same numbers), summarised in `cv_protocols_clean_315.md` |
| §4.3, Table 5 | Flow relations under the strict protocol, beside prior work | `python3 -m text2bpmn.paper_tables 5`; every prior system: `python3 -m text2bpmn.pet_strict` | `runs/final-3/pet_decisions`, `pet_no_llm`, `runs/final-2/pet_decisions`, `runs/ideas/idea1b/pet_pairs`, Neuberger et al.'s files | `tables/table5.md`, `text2bpmn/results/pet_strict_flow.md` (also the pairwise classifier's row: "pair questions, as submitted"); the comparators' pinned sources: `python3 -m text2bpmn.checks.table5_sources` → `runs/checks/final-3/open_analyses/table5_sources.md` |
| §4.3, Table 6 | the pairwise classifier on the 302 pairs | `python3 -m text2bpmn.paper_tables 6`; both labelling schemes: `python3 -m text2bpmn.rescore_false_branch_schemes` | `runs/final/table3_302`, `runs/final/corrected_302` | `tables/table6.md`, `text2bpmn/results/false_branch_schemes.md` |
| §4.4, Table 7 | lane assignment on PET | `python3 -m text2bpmn.paper_tables 7`; one run's lane scores: `python3 -m text2bpmn.lane_accuracy runs/final-3/coref_ablation --out <dir>`; GLiNER against BERT: `python3 -m text2bpmn.compare_gliner_arm --release` | `runs/final-3/coref_ablation`, `runs/gliner-3/lanes_gliner` | `tables/table7.md`, `tables/gliner_arm_comparison.md`; pronoun performers on the 7 unseen documents: `python3 -m text2bpmn.checks.unseen_pronoun_lanes` → `runs/checks/final-3/open_analyses/unseen_pronoun_lanes.md` |
| §4.5, Tables 8-9 | the relation stages on PET; the branch heads of PET's 75 decisions | `python3 -m text2bpmn.paper_tables 8` (`--woflan` checks the 180 models with WOFLAN again), `paper_tables 9`; the run's other analyses: `python3 -m text2bpmn.checks.method_analysis`; the decisions with and without an else-marker: `python3 -m text2bpmn.checks.else_marker_decisions` | `runs/final-3/pet_*`, `runs/final-2/pet_decisions`, `runs/ideas/idea1b/pet_pairs`, `runs/final/pet_classifier`, the WOFLAN records under `runs/checks/` | `tables/table8.md`, `table9.md`, `text2bpmn/results/method_analysis.md`, `runs/checks/final-3/open_analyses/else_marker_decisions.md` |
| §4.5 | repeated runs give identical counts on all 45 documents | `python3 -m text2bpmn.checks.repeated_runs` | the final method: `runs/ideas/idea3/pet_decisions4` (tag `relation-idea-3`) and `runs/final-3/pet_decisions`; pairwise classification: `runs/final/pet_classifier` and `runs/ideas/idea1b/pet_pairs` | prints only |
| §4.5 | tokens per question | `python3 -m text2bpmn.checks.token_usage` (downloads Qwen3.5's tokenizer at its pinned revision; stops with an error if its count disagrees with the server's log) | `runs/final-3/vllm.log`, the runs' records | `text2bpmn/results/token_usage.md` |
| §4.5.3 | the validity of the 282 models: BPMN 2.0.2 schema, WOFLAN, SHACL | the commands of step 6 above (SHACL takes 26 to 45 minutes) | the runs' models and ontologies | `runs/checks/final-3/{pet_models,xsd,soundness,shacl}/` |
| §4.6, Table 10 | the reference processes, with the footprint column | `python3 -m text2bpmn.paper_tables 10` (every loan row against the textbook reference, as the paper scores it); the loan rows against both references side by side: `python3 -m text2bpmn.checks.loan_rescore`; one model: `python3 -m text2bpmn.compare --reference <reference> --generated <run>/<case>/model.bpmn` and `python3 -m text2bpmn.behaviour` with the same arguments; the tasks left unmatched: `python3 -m text2bpmn.checks.unmatched_tasks` (both commands in step 5) | each run's `comparison.json` and `model.bpmn`; `text2bpmn/cases/*/reference*.bpmn` | `tables/table10.md`, `runs/checks/final-3/loan_reference/loan_rescore.md`, `runs/checks/final-3/unmatched_tasks/` |
| §4.6, Figs. 6-11 | the generated models and the references | `sh figures/section_4_6/commands.txt`, then `render_check` (step 4 above); a figure arranged by hand, checked against the model it shows: `python3 -m text2bpmn.checks.figure_models --dir <arranged files> --out figures/paper` | `runs/final-3/cases/*/model.bpmn`, `text2bpmn/cases/*/reference.bpmn` | `figures/section_4_6/*.{svg,png}`, `check.json` |
| §4.7, Tables 11-12 | the competency questions | the `cq_compare` command above; the queries: `text2bpmn/checks/cq/cq1.rq`-`cq8.rq` | the cases' ontologies, the references | `runs/checks/final-3/cq_compare/cq_compare.md`, `cq_answers.md` |
| §5 | the limitations | "Known limitations" below | – | – |

`tables/` is `runs/checks/final-3/tables/`.

**Where the drafts differ from the runs** (`runs/checks/final-3/tables/summary.md`):

- **Table 7, Tasks in Main Process.** BERT without FastCoref is 26 of 515 tasks,
  5.0%; the draft has 5.1%. GLiNER is 22 of 518, 4.2%; the draft has 4.3%. The
  drafts rounded the four-place shares of `lane_scores.json` (0.0505, 0.0425) a
  second time.
- **Table 8, this method's parallel pairs.** The runs give `5 of 10 (+1)`; the
  draft prints `5 of 10`. The draft's own rule brackets the pairs PET does not
  annotate, as in pairwise classification's `(+44)`. The one such pair
  (doc-3.5, one line of work split in two) is in the draft's text.
- **Section 4.5's text.** The pairwise classifier with its inserted gateways
  collapsed scores 0.676 pooled, as Table 8's strict column is. The draft's
  0.675 is the fold average.
- **The loan reference (D12).** It is now the textbook's Solution 3.2,
  `text2bpmn/cases/loan/reference.bpmn`: pool "Loan application", one exclusive
  and two parallel gateways, no exclusive join, |G| = 26. The paper's Table 10
  scores the four loan rows against it, and so does `paper_tables 10`. Which
  file holds which score, in each of the four loan folders
  (`runs/final-3/cases/loan`, `runs/final-3/cases_no_llm/loan`,
  `runs/gliner-3/cases_gliner/loan`, `runs/gliner-3/cases_gliner_no_llm/loan`):
  - `comparison.json` is the score against the textbook reference, made from
    the run's saved `model.bpmn` after the run;
  - `comparison_authored.json` is the run's own score against the reference it
    used, `reference_authored.bpmn` (|G| = 27). `paper_tables 10` checks that
    scoring that file again gives it.

  Both scores of every loan row are in
  `runs/checks/final-3/loan_reference/loan_rescore.md`.

**Not rebuilt from this repository alone:**

- Table 4's parameter counts need the weights. The table reads the committed
  record `runs/checks/final-3/tables/parameter_counts.json`, whose SHA-256s
  name the files counted. `python3 -m text2bpmn.checks.parameter_counts --check`
  recounts whatever weights are present.
- The pairwise classifier's PET run at `revision-final`
  (`runs/final/pet_classifier`) kept neither its answers nor its graphs. Its
  strict F1, parallel pairs and WOFLAN verdicts in Table 8 therefore come from
  its rerun, `runs/ideas/idea1b/pet_pairs`, which `paper_tables 8` checks has
  the same counts on all 45 documents.

### Generating the models (GPU)

The release runs served Qwen/Qwen3.5-27B-FP8 with vLLM 0.31.0 on one 44 GB GPU
(28.9 GiB of weights, 16,384-token context). The flags are the server's own
record of them, `runs/final-3/vllm.log`, line 8. The server loaded the Hub's
`main`, which was commit `97f5941b…` at the time: Qwen3.5's tokenizer at that
revision reproduces the logged prompt tokens exactly. To get the same weights,
pin it:

```bash
vllm serve Qwen/Qwen3.5-27B-FP8 \
    --revision 97f5941bf617e31c5e237364a8602ce3f03a551a \
    --tokenizer-revision 97f5941bf617e31c5e237364a8602ce3f03a551a \
    --port 11434 --max-model-len 16384 --max-num-seqs 16 --dtype bfloat16 \
    --no-enable-chunked-prefill --no-enable-prefix-caching \
    --structured-outputs-config '{"backend": "xgrammar", "disable_any_whitespace": true}'

# before a run: the server serves the model, decodes against the answer
# schemas, honours the length limit, writes no free whitespace, thinks not
python3 -m text2bpmn.remote.check_server --api-base http://localhost:11434/v1 \
    --model Qwen/Qwen3.5-27B-FP8
```

Serve it under its full id (no `--served-model-name`), since the run record
keeps only the served name. The server's environment is
`text2bpmn/remote/requirements-final.txt`.

Every setting of the release runs is `RunConfig`'s default
(`text2bpmn/run_config.py`), so a command without flags runs with them.
`text2bpmn/tests/test_run_config.py` compares the defaults with the release
record (`runs/final-3/cases/run_record.json`, `config`) field by field.

| Setting | Value |
|---|---|
| LLM | `hosted_vllm/Qwen/Qwen3.5-27B-FP8` at `http://localhost:11434/v1`, revision `97f5941bf617e31c5e237364a8602ce3f03a551a` |
| relation stage | `decisions4`: one question per decision and per concurrency word, with the soundness gate |
| decoding | temperature 0.0, seed 0, `max_tokens` 1024, thinking off, constrained output (JSON schema; reasoning at most 2,000 characters) |
| LLM cache | off (`--llm-cache` turns it on for development) |
| recogniser | `bert_ner_315_dev60` |
| ontology | `BPMNbasedOntologyV1_2.owl` (BBO, from `fetch_bbo`) |

The release runs themselves were made by two commands at the tag
`revision-final-3` of the development repository:
- `python3 -m text2bpmn.run_final` (34 minutes): PET with and without the LLM,
  the no-AND control, the case studies and the coreference ablation, written to
  `runs/final-3/`;
- `python3 -m text2bpmn.run_gliner_arm` (14 minutes): the fine-tuned GLiNER as
  recogniser, written to `runs/gliner-3/`.

Both refuse to start unless the code is clean and at that tag, so a rerun is
tied to the code that produced the results. Here, `--dry-run` tests them end
to end without a GPU (`python3 -m text2bpmn.run_final --dry-run --out <dir>`).
The PET experiments, which read PET's gold mentions, run without any weights.
The case studies and the coreference ablation need the BERT recogniser's
weights in place; without them those three experiments fail at "Loading NER".
The pipeline itself runs on any description with the release settings, as in
the next section.

## Running it on a new description

From the repository root, with the recogniser weights in place and the LLM
served as above:

```bash
# every stage at once: extraction, BPMN, SVG and PNG, the populated ontology and
# the competency questions; a reference is optional
text2bpmn/demo.sh my_description.txt out/ [reference.bpmn]

# description -> extraction JSON, BPMN 2.0 file and a drawing
python3 -m text2bpmn.finder3 text2bpmn/cases/goods_dispatch/input.txt \
        -o out.json --bpmn out.bpmn --svg out.svg

# draw a BPMN file (PNG and PDF need inkscape)
python3 -m text2bpmn.render out.bpmn -o out.svg --png out.png

# compare a generated model with a reference
python3 -m text2bpmn.compare --reference text2bpmn/cases/loan/reference.bpmn --generated out.bpmn
```

Without the LLM a run stops at startup. `--allow-no-llm` runs on regardless:
every answer is missing and the text order is the result, as in the no-LLM
controls. Every run records the commit, the settings, the LLM it asked and the
installed package versions in its output. Another model:
`--model hosted_vllm/<id> --api-base <url>/v1 [--model-revision <rev>]`.

## Tests

```bash
python3 -m pytest text2bpmn/tests -q
```

They use stand-ins for the models, so they need neither the weights nor the
LLM: after the two fetch steps of "Install" (BBO and Neuberger et al.'s files),
386 pass and 4 are skipped. Three of the skipped tests need the recogniser
weights or their training files; the fourth runs over saved outputs in the
repository root, which this repository does not have. Without the fetch steps,
365 pass and 25 are skipped: the other 21 need BBO or Neuberger et al.'s files.

## Known limitations

- An activity is assigned to the actor named in its own sentence, not through
  an extracted actor-performer relation. A sentence whose only actor is a
  bystander can therefore still place it wrongly.
- An activity's object is the nearest Activity Data span in its sentence.
  Where several activities share a sentence the wrong one can claim it, which is
  the largest single source of false-positive tasks.
- Relations are only sought forwards in the text, so loops and backward
  references cannot be expressed.
- The relation stage builds a parallel block only where the recogniser finds a
  concurrency word ("in the meantime"), with at most three lines of work, and
  does not ask about one inside a decision's branch. Concurrency the text does
  not mark with such a word is not modelled. A decision inside another
  decision's branch is not built.
- Data objects are not extracted; the models cover control flow, actors and
  activity metadata.
- Graph edit distance is an upper bound, from an optimal node assignment, not a
  proven minimum.
- The ontology step populates individuals; it does not add axioms or reasoning.

## Licence, third-party material and citation

The code and the authors' material are under the MIT licence (`LICENSE`).
Third-party material stays under its own terms; `THIRD_PARTY_NOTICES.md` lists
each item:
- the PET dataset (MIT, `third_party/pet/NOTICE`);
- the Camunda "Dispatch of goods" model and exercise text (academic and
  research use only, `third_party/camunda/NOTICE`);
- the textbook exercise and solution behind the loan case;
- the OMG BPMN 2.0.2 schemas.

BBO (GPL-3.0) and Neuberger et al.'s files are fetched and checked, not
redistributed. How to cite: `CITATION.cff`.
