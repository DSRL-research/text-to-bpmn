"""Train the BERT entity recogniser on the training pool, select on development.

    USE_TF=0 python3 -m text2bpmn.train_ner --out <model folder>

The recipe of checkpoint-564 (process-visualizer/src/token_classification_alex/
train.py): bert-base-cased, learning rate 2e-5 with linear decay and no warmup,
weight decay 0.01, batch 8, at most 15 epochs, early stopping after 3 epochs
without improvement, the best epoch kept; loss on each word's first sub-token
only; seqeval entity F1 as the selection metric. Two things differ, both on
purpose:

- checkpoint-564 trained on all 375 sentences of pet_train.json and validated
  on pet_test.json, so its early stopping and best-epoch choice were made on
  the 42 test sentences. Here it trains on the 315 sentences of
  text2bpmn/clean_split.py and validates on the 60 development sentences;
  the test split is never read.
- train.py created the model before seeding, so the classifier head was
  initialised from PyTorch's fixed default generator state, not from seed 42.
  Here the seed is set first.

The selected model is saved to --out, and train_record.json beside it records
the settings, every epoch's development scores, the selected epoch, the package
versions and the weights' checksum.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from text2bpmn.clean_split import split

LABELS = ["AND Gateway", "Activity", "Activity Data", "Actor", "Condition Specification",
          "Further Specification", "XOR Gateway"]
TAGS = ["O"] + [f"{prefix}-{label}" for label in LABELS for prefix in ("B", "I")]
RECIPE = {"base": "bert-base-cased", "learning_rate": 2e-5, "lr_scheduler_type": "linear",
          "warmup_ratio": 0.0, "weight_decay": 0.01, "batch_size": 8, "max_epochs": 15,
          "early_stopping_patience": 3, "seed": 42, "selection_metric": "seqeval entity F1 on dev"}


def _versions():
    import importlib.metadata as metadata
    out = {"python": sys.version.split()[0]}
    for package in ("transformers", "tokenizers", "torch", "numpy", "accelerate", "seqeval",
                    "safetensors", "huggingface-hub"):
        try:
            out[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            out[package] = None
    return out


def _revision(base):
    ref = Path.home() / ".cache/huggingface/hub" / f"models--{base.replace('/', '--')}" / "refs/main"
    return ref.read_text().strip() if ref.exists() else None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def train(out_dir, recipe=RECIPE):
    import numpy as np
    import torch
    from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
    from transformers import (AutoModelForTokenClassification, AutoTokenizer,
                              DataCollatorForTokenClassification, EarlyStoppingCallback,
                              Trainer, TrainingArguments, set_seed)

    started = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_records, dev_records = split()
    label2id = {tag: i for i, tag in enumerate(TAGS)}
    id2label = {i: tag for tag, i in label2id.items()}

    set_seed(recipe["seed"])  # before the model, so the classifier head is seeded too
    tokenizer = AutoTokenizer.from_pretrained(recipe["base"])
    model = AutoModelForTokenClassification.from_pretrained(
        recipe["base"], num_labels=len(TAGS), id2label=id2label, label2id=label2id)

    def encode(records):
        rows = []
        for record in records:
            encoded = tokenizer(record["tokens"], is_split_into_words=True, truncation=True)
            previous, labels = None, []
            for word in encoded.word_ids():
                if word is None or word == previous:
                    labels.append(-100)
                else:
                    labels.append(label2id[record["ner_tags"][word]])
                previous = word
            rows.append({**dict(encoded), "labels": labels})
        return rows

    def metrics(prediction):
        logits, gold = prediction
        predicted = np.argmax(logits, axis=-1)
        y_true = [[id2label[g] for p, g in zip(ps, gs) if g != -100] for ps, gs in zip(predicted, gold)]
        y_pred = [[id2label[p] for p, g in zip(ps, gs) if g != -100] for ps, gs in zip(predicted, gold)]
        return {"precision": precision_score(y_true, y_pred), "recall": recall_score(y_true, y_pred),
                "f1": f1_score(y_true, y_pred), "accuracy": accuracy_score(y_true, y_pred)}

    checkpoints = out_dir / "trainer"
    args = TrainingArguments(
        output_dir=str(checkpoints), learning_rate=recipe["learning_rate"],
        lr_scheduler_type=recipe["lr_scheduler_type"], warmup_ratio=recipe["warmup_ratio"],
        weight_decay=recipe["weight_decay"], per_device_train_batch_size=recipe["batch_size"],
        per_device_eval_batch_size=recipe["batch_size"], num_train_epochs=recipe["max_epochs"],
        seed=recipe["seed"], eval_strategy="epoch", save_strategy="epoch", save_total_limit=2,
        save_only_model=True, load_best_model_at_end=True, metric_for_best_model="f1",
        greater_is_better=True, logging_steps=10, report_to=[], disable_tqdm=True,
        use_cpu=not torch.cuda.is_available())
    trainer = Trainer(model=model, args=args, train_dataset=encode(train_records),
                      eval_dataset=encode(dev_records),
                      data_collator=DataCollatorForTokenClassification(tokenizer),
                      compute_metrics=metrics,
                      callbacks=[EarlyStoppingCallback(early_stopping_patience=recipe["early_stopping_patience"])])
    trainer.train()

    history = [{"epoch": round(h["epoch"]), "step": h["step"], "dev_f1": round(h["eval_f1"], 4),
                "dev_precision": round(h["eval_precision"], 4), "dev_recall": round(h["eval_recall"], 4),
                "dev_loss": round(h["eval_loss"], 4)}
               for h in trainer.state.log_history if "eval_f1" in h]
    best = max(history, key=lambda h: h["dev_f1"])  # the first epoch reaching the best, as the trainer keeps
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    (out_dir / "trainer_state.json").write_text(json.dumps(trainer.state.log_history, indent=2),
                                                encoding="utf-8")
    shutil.rmtree(checkpoints, ignore_errors=True)  # the selected weights are in out_dir

    record = {
        "recipe": recipe, "base_revision": _revision(recipe["base"]),
        "data": {"train": "text2bpmn/baselines/train_315.json (text2bpmn/clean_split.py)",
                 "train_sentences": len(train_records), "dev": "text2bpmn/baselines/dev_split.json",
                 "dev_sentences": len(dev_records), "test": "pet_test.json, not read"},
        "best_model_checkpoint": trainer.state.best_model_checkpoint,
        "selected_epoch": best["epoch"], "selected_step": best["step"], "selected_dev_f1": best["dev_f1"],
        "epochs_trained": max(h["epoch"] for h in history), "history": history,
        "model_dir": str(out_dir), "model_sha256": _sha256(out_dir / "model.safetensors"),
        "versions": _versions(), "platform": platform.platform(),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "minutes": round((time.time() - started) / 60, 1),
    }
    (out_dir / "train_record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="folder for the selected model and its record")
    args = ap.parse_args(argv)
    os.environ.setdefault("USE_TF", "0")
    record = train(args.out)
    print(json.dumps({k: v for k, v in record.items() if k != "history"}, indent=2))
    for h in record["history"]:
        print(f"   epoch {h['epoch']:2d}: dev F1 {h['dev_f1']:.4f}")


if __name__ == "__main__":
    main()
