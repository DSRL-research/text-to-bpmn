"""Fine-tune GLiNER on the same data as the BERT checkpoints.

    ~/.venvs/gliner-env/bin/python -m text2bpmn.gliner_finetune \
        --base urchade/gliner_small-v2.1 --name small-v2.1 \
        --train pet_train.json --dev text2bpmn/baselines/dev_split.json \
        --epochs 12 --out text2bpmn/baselines/finetuned

Run with the gliner environment's interpreter (text2bpmn/remote/requirements-gliner.txt).

Selection is on the development split and nothing else: after every epoch the
model is asked for its spans on dev, scored by text2bpmn/eval_ner.py over the
fixed label set, and kept only if its strict micro F1 improved. Training stops
when it has not improved for `--patience` epochs. The held-out split is never
read here.

Deviations from the parameter names in the GLiNER documentation, for this
version of the library (0.2.29), all recorded in the run record:

- `weight_decay_encoder` does not exist; the encoder's decay is `weight_decay`
  and the rest is `others_weight_decay`.
- `ner_labels` does not exist. The label set reaches the model through the data
  and through the negative types below, which is what it is for.
- `ner_negatives` is not a training argument but an argument of the collator, so
  hard negatives are passed per batch by wrapping it.
- `loss_type` already defaults to "focal" with `focal_loss_alpha=-1` and
  `focal_loss_gamma=0`, which is ordinary cross-entropy. Focal loss is therefore
  "enabled" by giving alpha and gamma real values.
"""
import argparse
import json
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from text2bpmn.eval_ner import entity_level, load_pet
from text2bpmn.pet_to_gliner import convert

# every label the corpus annotates, including the one it has almost none of
LABELS = ["Activity", "Activity Data", "Actor", "AND Gateway",
          "Condition Specification", "Further Specification", "XOR Gateway"]
# the pairs a model confuses here: a gateway marker against the condition it
# introduces, and an action against the thing acted on
HARD_NEGATIVES = ["XOR Gateway", "Condition Specification", "Activity", "Activity Data"]

DEFAULTS = dict(learning_rate=1e-5, others_lr=5e-5, per_device_train_batch_size=8,
                warmup_ratio=0.1, max_grad_norm=1.0, weight_decay=0.01,
                others_weight_decay=0.01)


def dev_spans(model, sentences, labels, threshold):
    """The model's spans on each sentence, in the evaluator's shape."""
    out = []
    for text in sentences:
        found = model.predict_entities(text, labels, threshold=threshold)
        out.append([{"start": int(e["start"]), "end": int(e["end"]),
                     "label": e["label"], "score": float(e["score"])} for e in found])
    return out


def dev_f1(model, dev, labels, threshold, scope):
    """Strict micro F1 on the development split, the only selection signal."""
    sentences = [text for text, _, _, _ in dev]
    predicted = dev_spans(model, sentences, labels, threshold)
    documents = [(gold, found) for (_, gold, _, _), found in zip(dev, predicted)]
    strict = entity_level(documents, "strict", scope=scope)
    relaxed = entity_level(documents, "relaxed", scope=scope)
    return strict["micro"]["f1"], relaxed["micro"]["f1"]


def build(base_model, focal, negatives, seed, output_dir, epochs, **overrides):
    from gliner import GLiNER
    from gliner.data_processing import UniEncoderSpanDataCollator
    from gliner.training import TrainingArguments

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    model = GLiNER.from_pretrained(base_model)
    collator = UniEncoderSpanDataCollator(model.config, data_processor=model.data_processor,
                                          prepare_labels=True)
    if negatives:
        inner = collator

        class WithHardNegatives:
            """The confusable classes are offered as candidates in every batch."""
            def __call__(self, batch, **kwargs):
                return inner(batch, negatives=list(negatives), **kwargs)

        collator = WithHardNegatives()

    settings = {**DEFAULTS, **overrides}
    args = TrainingArguments(
        output_dir=str(output_dir), num_train_epochs=epochs, seed=seed,
        focal_loss_alpha=focal[0] if focal else -1,
        focal_loss_gamma=focal[1] if focal else 0,
        eval_strategy="no", save_strategy="no", logging_steps=25,
        report_to=[], use_cpu=not torch.cuda.is_available(), **settings)
    return model, collator, args, settings


class DevSelection:
    """Score dev after every epoch, keep the best, stop when it stalls.

    A callback rather than a loop of one-epoch runs: restarting the Trainer each
    epoch would reset the optimiser and replay the warmup every time.
    """

    def __init__(self, model, dev, labels, scope, threshold, out_dir, patience):
        self.model, self.dev, self.labels = model, dev, labels
        self.scope, self.threshold = scope, threshold
        self.out_dir, self.patience = out_dir, patience
        self.history, self.best, self.best_epoch, self.waited = [], -1.0, 0, 0
        self.started = time.time()

    def on_epoch_end(self, args, state, control, **kwargs):
        was_training = self.model.training
        self.model.eval()
        with torch.no_grad():
            strict, relaxed = dev_f1(self.model, self.dev, self.labels,
                                     self.threshold, self.scope)
        if was_training:
            self.model.train()
        epoch = round(state.epoch or 0)
        self.history.append({"epoch": epoch, "dev_strict_micro_f1": strict,
                             "dev_relaxed_micro_f1": relaxed,
                             "minutes": round((time.time() - self.started) / 60, 1)})
        print(f"   epoch {epoch}: dev strict {strict} relaxed {relaxed} "
              f"({self.history[-1]['minutes']} min)", flush=True)
        if strict > self.best:
            self.best, self.best_epoch, self.waited = strict, epoch, 0
            self.model.save_pretrained(str(self.out_dir / "best"))
        else:
            self.waited += 1
            if self.waited >= self.patience:
                print(f"   no improvement for {self.patience} epochs; stopping", flush=True)
                control.should_training_stop = True
        return control

    def __getattr__(self, name):  # the other callback hooks are not needed
        if name.startswith("on_"):
            return lambda *a, **k: k.get("control")
        raise AttributeError(name)


def train(base_model, name, train_path, dev_path, out_dir, epochs=12, patience=3,
          focal=None, negatives=None, seed=0, threshold=0.5, labels=LABELS, **overrides):
    from gliner.training import Trainer

    out_dir = Path(out_dir) / name
    out_dir.mkdir(parents=True, exist_ok=True)
    train_examples = convert(train_path)
    dev = load_pet(dev_path)
    scope = sorted(labels)

    model, collator, args, settings = build(base_model, focal, negatives, seed,
                                           out_dir / "trainer", epochs, **overrides)
    selection = DevSelection(model, dev, labels, scope, threshold, out_dir, patience)
    trainer = Trainer(model=model, args=args, data_collator=collator,
                      train_dataset=train_examples,
                      processing_class=model.data_processor.transformer_tokenizer,
                      callbacks=[selection])
    trainer.train()

    record = {
        "name": name, "base_model": base_model,
        "parameters_millions": round(sum(p.numel() for p in model.parameters()) / 1e6, 1),
        "labels": labels,
        "focal_loss": {"alpha": focal[0], "gamma": focal[1]} if focal else None,
        "hard_negatives": negatives, "seed": seed,
        "epochs_requested": epochs, "epochs_scored": len(selection.history),
        "best_epoch": selection.best_epoch,
        "best_dev_strict_micro_f1": selection.best,
        "inference_threshold": threshold,
        "training_arguments": dict(settings),
        "train_data": str(train_path), "train_sentences": len(train_examples),
        "dev_data": str(dev_path), "dev_sentences": len(dev),
        "history": selection.history,
        "minutes": round((time.time() - selection.started) / 60, 1),
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "torch": torch.__version__, "cuda": torch.cuda.is_available(),
        "best_model_dir": str(out_dir / "best"),
    }
    (out_dir / "run.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--train", default="pet_train.json")
    ap.add_argument("--dev", default="text2bpmn/baselines/dev_split.json")
    ap.add_argument("--out", default="text2bpmn/baselines/finetuned")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--focal", nargs=2, type=float, metavar=("ALPHA", "GAMMA"),
                    help="enable focal loss with this alpha and gamma")
    ap.add_argument("--hard-negatives", action="store_true",
                    help="offer the confusable classes as candidates in every batch")
    args = ap.parse_args()

    record = train(args.base, args.name, args.train, args.dev, args.out,
                   epochs=args.epochs, patience=args.patience,
                   focal=tuple(args.focal) if args.focal else None,
                   negatives=HARD_NEGATIVES if args.hard_negatives else None,
                   seed=args.seed, threshold=args.threshold)
    print(json.dumps({k: v for k, v in record.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
