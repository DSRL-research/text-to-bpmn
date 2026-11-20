# Table 4's parameter counts, from the weights

Run 2026-11-17T15:01:37+00:00 at revision-final-3-28-g03c8cd0 (03c8cd0, dirty: False); lxml 5.2.1, pm4py 2.7.19.2, rdflib 7.5.0, owlready2 0.49, dspy 3.1.2, transformers 4.50.0.dev0.

Elements of every tensor each weights file stores (safetensors header, or the tensor sizes of a PyTorch pickle read without running it); `text2bpmn/checks/parameter_counts.py`. M = 10^6.

| configuration | parameters | M | tensors | training run's own count (M) | weights | SHA-256 |
|---|---|---|---|---|---|---|
| BERT, fine-tuned | 107,731,215 | 107.7 | 199 | – | `process-visualizer/src/token_classification_alex/bert_ner_315_dev60/model.safetensors` | `e17e92268b8fae65…` |
| GLiNER small v2.1, fine-tuned | 152,648,704 | 152.6 | 128 | 152.6 | `text2bpmn/baselines/finetuned_315/A-small-v2.1-315/best/pytorch_model.bin` | `1afa6921385ac326…` |
| GLiNER medium v2.1, fine-tuned | 195,175,936 | 195.2 | 224 | 195.2 | `text2bpmn/baselines/finetuned_315/B-medium-v2.1-315/best/pytorch_model.bin` | `b56fdfacc0d9d914…` |
| GLiNER, focal loss | 152,648,704 | 152.6 | 128 | 152.6 | `text2bpmn/baselines/finetuned_315/C-small-focal-315/best/pytorch_model.bin` | `7664a614e12cc418…` |
| GLiNER, hard negatives | 152,648,704 | 152.6 | 128 | 152.6 | `text2bpmn/baselines/finetuned_315/D-small-hardneg-315/best/pytorch_model.bin` | `1459dabdf24ef220…` |
| GLiNER medium v2.1, zero-shot | 195,175,936 | 195.2 | 224 | – | `hf://urchade/gliner_medium-v2.1@40ec419335d09393f298636f471328b722c6da9e/model.safetensors` | `922214c0c60f7835…` |
| GLiNER2.5 base v1, zero-shot | 193,581,591 | 193.6 | 334 | – | `hf://fastino/gliner2.5-base-v1@ca906247640776a07753514055be9726f9080ead/model.safetensors` | `7274094de2e0c2a3…` |
