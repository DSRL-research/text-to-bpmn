"""Five-fold cross-validation over the PET training portion, for either model.

    ~/.venvs/gliner-env/bin/python -m text2bpmn.cross_validate --model gliner \
        --base urchade/gliner_small-v2.1 --epochs 10 \
        --name gliner-small --out text2bpmn/baselines/cv

`--base` is the **pretrained** checkpoint, never a model already fine-tuned on
this corpus: that model saw all 375 sentences, so every fold's held-out part is
in its training data, and the folds would measure nothing.
    python3 -m text2bpmn.cross_validate --model bert \
        --base bert-base-cased --epochs 9 --name bert --out text2bpmn/baselines/cv

The folds are defined in `text2bpmn/baselines/cv_folds.json`: grouped by
document, so no document's sentences straddle the split, and with the
development sentences excluded, since the epoch budget was chosen on those.

The budget is fixed and there is no early stopping inside a fold: the number of
epochs was already chosen on the development split, so selecting again inside
each fold would be selecting on the data the fold exists to measure. Both models
therefore get the same treatment, and the spread reported is the spread of
training, not of a second round of tuning.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from text2bpmn.eval_ner import entity_level, load_pet
from text2bpmn.pet_to_gliner import convert, to_gliner

LABELS = ["Activity", "Activity Data", "Actor", "AND Gateway",
          "Condition Specification", "Further Specification", "XOR Gateway"]


def folds(path="text2bpmn/baselines/cv_folds.json"):
    """The fold definition. `cv_folds_full.json` covers the whole PET corpus,
    which is what a published PET baseline uses; `cv_folds.json` excludes the
    development sentences and is the stricter variant."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    return spec, spec["fold_sentence_indices"]


def pet_records(path="pet_train.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _score(documents, scope):
    return {criterion: entity_level(documents, criterion, scope=scope)
            for criterion in ("strict", "relaxed")}


def gliner_fold(base, train_records, test_records, epochs, seed, threshold, out_dir):
    """Fine-tune on the training folds, then score the held-out fold."""
    import torch
    from gliner import GLiNER
    from gliner.data_processing import UniEncoderSpanDataCollator
    from gliner.training import Trainer, TrainingArguments

    from text2bpmn.gliner_finetune import DEFAULTS

    torch.manual_seed(seed)
    model = GLiNER.from_pretrained(base)
    examples = [to_gliner(r["tokens"], r["ner_tags"]) for r in train_records]
    collator = UniEncoderSpanDataCollator(model.config, data_processor=model.data_processor,
                                          prepare_labels=True)
    args = TrainingArguments(output_dir=str(out_dir), num_train_epochs=epochs, seed=seed,
                             eval_strategy="no", save_strategy="no", report_to=[],
                             use_cpu=not torch.cuda.is_available(), disable_tqdm=True,
                             logging_steps=50, **DEFAULTS)
    Trainer(model=model, args=args, data_collator=collator, train_dataset=examples,
            processing_class=model.data_processor.transformer_tokenizer).train()

    model.eval()
    documents = []
    for record in test_records:
        text, gold = _gold(record)
        with torch.no_grad():
            found = model.predict_entities(text, LABELS, threshold=threshold)
        documents.append((gold, [{"start": int(e["start"]), "end": int(e["end"]),
                                  "label": e["label"], "score": float(e["score"]),
                                  "tokens": text[int(e["start"]):int(e["end"])].split()}
                                 for e in found]))
    return documents


def bert_fold(base, train_records, test_records, epochs, seed, out_dir, warmup_ratio=0.1,
              seed_model=False):
    """The same folds for the fine-tuned token classifier, so the spreads compare.

    The defaults are the recipe of the October runs (warmup 0.1, the model
    created before seeding, so its head starts from PyTorch's default state). text2bpmn/train_ner.py, the recogniser the pipeline uses,
    trains with no warmup and seeds first: `warmup_ratio=0, seed_model=True`
    with seed 42 runs the folds with exactly that recipe.
    """
    import numpy as np
    import torch
    from transformers import (AutoModelForTokenClassification, AutoTokenizer,
                              DataCollatorForTokenClassification, Trainer,
                              TrainingArguments, pipeline)

    tags = ["O"] + [f"{prefix}-{label}" for label in LABELS for prefix in ("B", "I")]
    label2id = {tag: index for index, tag in enumerate(tags)}
    if seed_model:
        from transformers import set_seed
        set_seed(seed)  # before the model, so the classifier head is seeded too
    tokenizer = AutoTokenizer.from_pretrained(base)
    model = AutoModelForTokenClassification.from_pretrained(
        base, num_labels=len(tags), id2label={i: t for t, i in label2id.items()},
        label2id=label2id)

    def encode(records):
        rows = []
        for record in records:
            encoded = tokenizer(record["tokens"], is_split_into_words=True, truncation=True)
            previous, labels = None, []
            for word in encoded.word_ids():
                if word is None:
                    labels.append(-100)
                elif word != previous:
                    labels.append(label2id.get(record["ner_tags"][word], 0))
                else:
                    labels.append(-100)
                previous = word
            rows.append({**{k: v for k, v in encoded.items()}, "labels": labels})
        return rows

    args = TrainingArguments(output_dir=str(out_dir), num_train_epochs=epochs,
                             per_device_train_batch_size=8, learning_rate=2e-5,
                             weight_decay=0.01, warmup_ratio=warmup_ratio, max_grad_norm=1.0,
                             eval_strategy="no", save_strategy="no", report_to=[],
                             seed=seed, use_cpu=not torch.cuda.is_available(),
                             disable_tqdm=True, logging_steps=50)
    Trainer(model=model, args=args, train_dataset=encode(train_records),
            data_collator=DataCollatorForTokenClassification(tokenizer)).train()

    recogniser = pipeline("token-classification", model=model.eval(), tokenizer=tokenizer,
                          aggregation_strategy="simple", device=-1)
    documents = []
    for record in test_records:
        text, gold = _gold(record)
        found = [{"start": int(e["start"]), "end": int(e["end"]),
                  "label": e["entity_group"], "score": float(e["score"]),
                  "tokens": text[int(e["start"]):int(e["end"])].split()}
                 for e in recogniser(text)]
        documents.append((gold, found))
    return documents


def _gold(record):
    from text2bpmn.eval_ner import spans_from_bio
    return spans_from_bio(record["tokens"], record["ner_tags"])


def run(kind, base, name, epochs, out_dir, seed=0, threshold=0.5, scope=None,
        folds_path="text2bpmn/baselines/cv_folds.json", records_path="pet_train.json",
        warmup_ratio=0.1, seed_model=False):
    scope = sorted(scope or LABELS)
    spec, fold_indices = folds(folds_path)
    records = pet_records(records_path)
    out_dir = Path(out_dir) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # a fold already recorded is not run again, so an interrupted run (a laptop
    # suspending on low battery, say) resumes instead of starting over
    done_path = out_dir / "folds.json"
    per_fold = json.loads(done_path.read_text(encoding="utf-8")) if done_path.exists() else []
    finished = {entry["fold"] for entry in per_fold}
    if finished:
        print(f"resuming: folds {sorted(finished)} already recorded", flush=True)
    started = time.time()
    for held_out, indices in enumerate(fold_indices):
        if held_out in finished:
            continue
        train_indices = [i for f, fold in enumerate(fold_indices) if f != held_out for i in fold]
        train_records = [records[i] for i in train_indices]
        test_records = [records[i] for i in indices]
        print(f"fold {held_out}: train {len(train_records)}, test {len(test_records)}", flush=True)
        worker = gliner_fold if kind == "gliner" else bert_fold
        extra = (threshold, out_dir / f"fold{held_out}") if kind == "gliner" \
            else (out_dir / f"fold{held_out}", warmup_ratio, seed_model)
        documents = worker(base, train_records, test_records, epochs, seed, *extra)
        scores = _score(documents, scope)
        # saved so another protocol can score the same predictions without
        # training anything again
        (out_dir / f"predictions_fold{held_out}.json").write_text(json.dumps(
            [{"document": records[i].get("document name"),
              "gold": g, "predicted": p}
             for i, (g, p) in zip(indices, documents)], ensure_ascii=False), encoding="utf-8")
        per_fold.append({"fold": held_out, "train": len(train_records), "test": len(test_records),
                         "strict_micro_f1": scores["strict"]["micro"]["f1"],
                         "relaxed_micro_f1": scores["relaxed"]["micro"]["f1"],
                         "strict_per_label": {l: scores["strict"]["per_label"][l]["f1"] for l in scope},
                         "minutes": round((time.time() - started) / 60, 1)})
        print(f"   strict {per_fold[-1]['strict_micro_f1']} "
              f"relaxed {per_fold[-1]['relaxed_micro_f1']}", flush=True)
        (out_dir / "folds.json").write_text(json.dumps(per_fold, indent=2), encoding="utf-8")

    def summarise(key):
        values = [f[key] for f in per_fold]
        return {"mean": round(statistics.mean(values), 3),
                "sd": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
                "folds": values}

    record = {"kind": kind, "base": base, "name": name, "epochs": epochs, "seed": seed,
              "warmup_ratio": warmup_ratio if kind == "bert" else None,
              "seed_before_model": seed_model if kind == "bert" else None,
              "folds_definition_file": folds_path, "records": records_path,
              "threshold": threshold if kind == "gliner" else None,
              "labels": scope, "folds_definition": {k: v for k, v in spec.items()
                                                    if k != "fold_sentence_indices"},
              "strict_micro_f1": summarise("strict_micro_f1"),
              "relaxed_micro_f1": summarise("relaxed_micro_f1"),
              "per_fold": per_fold,
              "minutes": round((time.time() - started) / 60, 1)}
    (out_dir / "cv.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", choices=("gliner", "bert"), required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--epochs", type=int, required=True,
                    help="the budget chosen on the development split; no early stopping here")
    ap.add_argument("--out", default="text2bpmn/baselines/cv")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--folds", default="text2bpmn/baselines/cv_folds.json")
    ap.add_argument("--records", default="pet_train.json")
    ap.add_argument("--warmup-ratio", dest="warmup_ratio", type=float, default=0.1,
                    help="BERT only; 0 is the recipe of text2bpmn/train_ner.py")
    ap.add_argument("--seed-model", dest="seed_model", action="store_true",
                    help="BERT only: seed before creating the model, as train_ner.py does")
    args = ap.parse_args()
    record = run(args.model, args.base, args.name, args.epochs, args.out,
                 args.seed, args.threshold, folds_path=args.folds,
                 records_path=args.records, warmup_ratio=args.warmup_ratio,
                 seed_model=args.seed_model)
    print(json.dumps({k: v for k, v in record.items() if k != "per_fold"}, indent=2))


if __name__ == "__main__":
    main()
