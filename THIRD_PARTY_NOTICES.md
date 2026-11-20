# Third-party material

What this repository contains or uses from others, under which terms, and
whether a copy is here. None of it is covered by the repository's own licence
(`LICENSE`, MIT). The licences are as their sources state them (dataset and
model cards, repository files, package metadata), checked in November 2026;
this is a record of them, not legal advice.

## Included in this repository

| Component | Terms | Source | Files here |
|---|---|---|---|
| **PET dataset v1.1** (Bellan et al., NL4AI 2022) | MIT, as its dataset card's metadata declares; the card names no copyright holder | https://huggingface.co/datasets/patriziobellan/PET (card revision `5eb9bca5c7dc850b2a42df268b78b88190ab2466`) | `pet_data/PETv1.1-relations.json`; converted: `pet_train.json`, `pet_test.json`, `text2bpmn/baselines/train_315.json`, `dev_split.json`, `dev_split_definition.json`, `pet_jobs.json`, the span files under `text2bpmn/baselines/`; the pipeline's outputs on PET's texts under `runs/`. Notice and licence text: **`third_party/pet/NOTICE`** |
| **Camunda "BPMN for Research": the "Dispatch of goods" model solution** | academic and research use only; the link https://github.com/camunda/bpmn-for-research must be kept; no commercial use (the repository's README; it has no licence file) | https://github.com/camunda/bpmn-for-research at `1416f6f2104ae597eafa3097946140ebc2136a53`, `BPMN for Research/English/01-Dispatch-of-goods/03-Solution/Dispatch-of-goods.bpmn` | `text2bpmn/cases/goods_dispatch/reference.bpmn`, byte-identical (SHA-256 `bae9ed647ee86d46a8389d1099d06857aa0aee12181cb01ae4ac449e8b198436`). Details and every derived file: **`third_party/camunda/NOTICE`** |
| **Camunda "BPMN for Research": the "Dispatch of goods" exercise text** | the same terms | the same commit, `01-Exercise/dispatch of goods - exercise.pdf` (SHA-256 `1500eeb0fcc6627b43274d4a0c12997190e44bfe76233e3b82e49ea252859361`) | verbatim: **`third_party/camunda/dispatch-of-goods_exercise.txt`**; reworded, the case's input: `text2bpmn/cases/goods_dispatch/input.txt` (the differences are listed in `third_party/camunda/NOTICE`) |
| **Textbook exercise and solution: Exercise 3.2 and its Solution 3.2** in M. Dumas, M. La Rosa, J. Mendling, H. A. Reijers, *Fundamentals of Business Process Management*, 2nd ed., Springer, 2018 | no licence; the publisher's rights are not licensed by this repository. Quoted for research. | the book | the exercise's text: `text2bpmn/cases/loan/input.txt`. The solution, transcribed by the authors with the textbook's labels verbatim and its control flow (pool name and layout are the authors'): `text2bpmn/cases/loan/reference.bpmn`, built by `text2bpmn/cases/loan/build_textbook_reference.py`; its drawing `figures/section_4_6/loan_reference.*`. The pipeline's outputs on the text repeat parts of it (the `loan` folders under `runs/`). `text2bpmn/cases/loan/reference_authored.bpmn`, the reference the release runs were first scored against, was modelled by the authors from the exercise text (`text2bpmn/cases/loan/build_reference.py`) |
| **OMG BPMN 2.0.2 XML schemas** (OMG document formal/13-12-09, https://www.omg.org/spec/BPMN/2.0.2/; the machine-readable files are those dated 20100501) | OMG's terms for its specifications; the files carry no licence header | https://www.omg.org/spec/BPMN/20100501/ | `text2bpmn/checks/schemas/`, unmodified, used by `text2bpmn/checks/xsd_validate.py`: `BPMN20.xsd` (`a07c159cb0594573dd7c97b1370dd116112378f377e43c89a8bf512ac5030705`), `Semantic.xsd` (`c4318842f7d2bbc262d7954c9452c501db16f0868eac0b8732ec5d7fb384d9a7`), `BPMNDI.xsd` (`f0dff1cd559d1514d8ebfc8c646f58402bcaced27ec22e2aa6456c2dcc80b038`), `DC.xsd` (`a2f90e5ad9bb48c6915e4e034b4e27ac838264a1d4f27bfc70dbdfc69351312d`), `DI.xsd` (`8220b179c175572df74e08a51bffabe957867962035cee7b5fee0b6acb4c4498`). `BPMN20.xsd` includes `Semantic.xsd` and imports `BPMNDI.xsd`, which imports the other two, so the five stay together |

The healthcare case (`text2bpmn/cases/healthcare/input.txt`, `reference.bpmn`)
is not third-party material: the care-pathway description and its reference
model were written by the project's domain experts (Niculae Stancioiu Heart
Institute, Cluj-Napoca), are published here with their approval, and fall
under the repository's licence.

## Distributed with the archive, not in git

The two recognisers' weights are deposited on Zenodo, not committed; the
deposit and its DOI are in `README.md`, "The recogniser weights":

- **bert-base-cased** (Google; Apache-2.0, https://huggingface.co/bert-base-cased,
  revision `cd5ef92a9fb2f889e972770a36d4ed042daf221e`): the base of the
  recogniser `bert_ner_315_dev60`. Its folder on Zenodo carries bert-base-cased's
  **tokenizer files** (`vocab.txt`, `tokenizer.json`, `tokenizer_config.json`,
  `special_tokens_map.json`), saved with the fine-tuned weights, which are a
  derivative of bert-base-cased; Apache-2.0's notice requirements apply there.
  This repository contains no bert-base-cased file; its training record is
  `text2bpmn/baselines/bert_ner_315_dev60/train_record.json`.
- **GLiNER** `urchade/gliner_small-v2.1` (Zaratiana et al., NAACL 2024;
  Apache-2.0, https://huggingface.co/urchade/gliner_small-v2.1): the base of
  GLiNER configuration A (`A-small-v2.1-315`), whose fine-tuned weights and
  tokenizer are on Zenodo; its training record is
  `text2bpmn/baselines/finetuned_315/A-small-v2.1-315/run.json`.

## Fetched and checked, not redistributed

| Component | Licence | Source | How |
|---|---|---|---|
| BBO, the BPMN Based Ontology (Annane, Aussenac, Kamel, 2019), and its SHACL shapes | GPL-3.0 | https://github.com/AminaANNANE/BBO_BPMNbasedOntology at `cb835bbac1f603d0c59a360322400cae50677039` | `python3 -m text2bpmn.checks.fetch_bbo` fetches the pinned commit and checks the SHA-256 of every file; git-ignored. The populated ontologies under `runs/` hold only individuals and import BBO by IRI |
| Neuberger et al.'s PET conversion, folds and stored system outputs (CoopIS 2023, arXiv:2305.03960; ER 2024, arXiv:2407.18540) | none stated (no licence file) | https://github.com/JulianNeuberger/pet-baselines at `d8310d4df71c2d4fba652711577ba1d6807da0c6`; https://github.com/JulianNeuberger/llm-process-generation at `21f190b8417e249c3f271d95d4497e3f1f4243ef` | `python3 -m text2bpmn.pet_strict --fetch`, checked against `text2bpmn/baselines/neuberger_sources.json` (path and SHA-256 of all 33 files); git-ignored. Only scores computed from them are committed (`text2bpmn/results/pet_strict_flow.md`) |

## Used, not redistributed

| Component | Licence | How it is used |
|---|---|---|
| Qwen3.5-27B-FP8 (Qwen Team, 2026), https://huggingface.co/Qwen/Qwen3.5-27B-FP8, revision `97f5941bf617e31c5e237364a8602ce3f03a551a` | Apache-2.0 (model card) | the LLM of the release runs, served by vLLM; its tokenizer counts the prompt tokens (`text2bpmn/checks/token_usage.py`) |
| GLiNER library (https://github.com/urchade/GLiNER) | Apache-2.0 | the alternative recogniser (`text2bpmn/gliner_finetune.py`, `gliner_baseline.py`), in its own environment (`text2bpmn/remote/requirements-gliner.txt`) |
| FastCoref (Otmazgin, Cattan, Goldberg, AACL-IJCNLP 2022) and its model `biu-nlp/f-coref` | MIT | the pipeline's coreference step; downloaded at run time |
| pm4py | AGPL-3.0 | the check scripts only (WOFLAN soundness, footprints); the pipeline does not import it |
| vLLM, DSPy, transformers, spaCy and `en_core_web_sm`, owlready2, rdflib, pyshacl, lxml, PyTorch | Apache-2.0, MIT, Apache-2.0, MIT, LGPL-3.0-or-later, BSD-3-Clause, Apache-2.0, BSD-3-Clause; PyTorch BSD-3-Clause with bundled parts under other licences (its package metadata) | installed from their package indexes (`requirements.txt`, `text2bpmn/remote/requirements-*.txt`) |
