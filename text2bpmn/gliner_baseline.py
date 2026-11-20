"""Zero-shot entity recognition with GLiNER, as a baseline for the fine-tuned models.

    python3 -m text2bpmn.gliner_baseline --model urchade/gliner_medium-v2.1 \
        --api gliner --phrasing terse --data pet_test.json --out spans.json

Run with the interpreter of the environment that holds the library
(text2bpmn/remote/requirements-gliner.txt): the GLiNER releases need incompatible
versions of `transformers`, and neither may be installed over the one this
project's own measurements were made with.

Spans come out in the shape text2bpmn/eval_ner.py scores,
`[{start, end, label, score}]`, with GLiNER's own character offsets and the
prompt mapped back to its PET label. Nothing passes through finder3's
`_clean_and_validate_activity` or `_clean_name`, which rewrite a span's text
without moving its offsets.

Every span the model returns at or above FLOOR is saved with its score, so a
threshold can be chosen afterwards without running the model again. That is
what keeps the held-out set to a single pass.
"""
import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FLOOR = 0.3  # the lowest threshold swept; everything at or above it is kept

# PET label -> the text GLiNER is prompted with. Three phrasings, chosen on dev only.
PHRASINGS = {
    # one or two words, the label as it stands
    "terse": {
        "Activity": "activity",
        "Activity Data": "activity data",
        "Actor": "actor",
        "Condition Specification": "condition specification",
        "Further Specification": "further specification",
        "XOR Gateway": "exclusive gateway",
    },
    # a description of the class in ordinary words
    "descriptive": {
        "Activity": "task or action performed in the process",
        "Activity Data": "object or data an action is performed on",
        "Actor": "person, role or system performing an action",
        "Condition Specification": "condition under which a branch is taken",
        "Further Specification": "additional detail about how an action is performed",
        "XOR Gateway": "word marking a choice between alternatives",
    },
    # the annotation scheme's own wording of each type
    "scheme": {
        "Activity": "action verb",
        "Activity Data": "object of an action",
        "Actor": "participant",
        "Condition Specification": "the logic rule of a branch",
        "Further Specification": "further specification of an action",
        "XOR Gateway": "conditional branching logic marker",
    },
}

# a fine-tuned model is asked for the label names it was trained on, so the
# prompt is the label itself and nothing is being paraphrased
TRAINED_LABELS = ["Activity", "Activity Data", "Actor", "AND Gateway",
                  "Condition Specification", "Further Specification", "XOR Gateway"]
PHRASINGS["identity"] = {label: label for label in TRAINED_LABELS}

# step 5: concurrency only, the labels the four-label checkpoint cannot express
PARALLEL_PROBE = {
    "AND Gateway": "parallel gateway",
    "parallel flow": "parallel flow",
    "concurrent activities": "concurrent activities",
    "activities performed simultaneously": "activities performed simultaneously",
}


def load_sentences(path):
    """[(identifier, text)] from a PET split, or one text per line from a .txt."""
    path = Path(path)
    if path.suffix.lower() == ".txt":
        return [(path.stem, " ".join(path.read_text(encoding="utf-8").split()))]
    raw = path.read_text(encoding="utf-8")
    try:
        records = json.loads(raw)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return [(f"{record.get('document name', '?')}#{index}", " ".join(record["tokens"]))
            for index, record in enumerate(records)]


def _versions(packages):
    import importlib.metadata as metadata
    out = {}
    for package in packages:
        try:
            out[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            out[package] = None
    return out


def _revision(repo):
    """The commit the weights were downloaded at, for the run record."""
    try:
        from huggingface_hub import HfApi
        return HfApi().model_info(repo).sha
    except Exception as error:
        return f"unknown ({type(error).__name__})"


def predict_gliner(model_name, texts, prompts, seed):
    """urchade/* and gliner-community/* checkpoints, through the `gliner` library."""
    import torch
    from gliner import GLiNER

    torch.manual_seed(seed)
    model = GLiNER.from_pretrained(model_name, load_tokenizer=True).eval()
    labels = list(prompts.values())
    out = []
    for text in texts:
        found = model.predict_entities(text, labels, threshold=FLOOR)
        out.append([{"start": int(e["start"]), "end": int(e["end"]),
                     "label": e["label"], "score": round(float(e["score"]), 4)}
                    for e in found])
    return out, {"library": "gliner", **_versions(["gliner", "transformers", "torch"])}


def predict_gliner2(model_name, texts, prompts, seed):
    """fastino/gliner2.5-* checkpoints, through the `gliner2` library's AutoExtractor."""
    import torch
    from gliner2 import AutoExtractor

    torch.manual_seed(seed)
    model = AutoExtractor.from_pretrained(model_name)
    labels = list(prompts.values())
    out = []
    for text in texts:
        # without these the library returns neither offsets nor scores, and the
        # spans could then only be located by searching for their text
        found = model.extract_entities(text, labels, threshold=FLOOR,
                                       include_spans=True, include_confidence=True)
        out.append(_normalise_gliner2(found, text))
    return out, {"library": "gliner2", **_versions(["gliner2", "transformers", "torch"])}


def _normalise_gliner2(found, text):
    """gliner2 groups its answer by label and may omit offsets; recover them.

    A span without offsets is located by its text, left to right, so repeated
    mentions each get their own position rather than all collapsing onto the
    first.
    """
    spans, used = [], []
    entities = found.get("entities", found) if isinstance(found, dict) else found
    if isinstance(entities, dict):
        flat = [(label, item) for label, items in entities.items() for item in items]
    else:
        flat = [(item.get("label"), item) for item in entities]
    for label, item in flat:
        if isinstance(item, dict) and item.get("start") is not None:
            start, end = int(item["start"]), int(item["end"])
        else:
            surface = item["text"] if isinstance(item, dict) else str(item)
            start = -1
            for candidate in _occurrences(text, surface):
                if candidate not in used:
                    start = candidate
                    break
            if start < 0:
                continue
            used.append(start)
            end = start + len(surface)
        # gliner2 names it "confidence"; the gliner library names it "score"
        score = float(item.get("confidence", item.get("score", 1.0))) \
            if isinstance(item, dict) else 1.0
        spans.append({"start": start, "end": end, "label": label,
                      "score": round(score, 4)})
    return spans


def _occurrences(text, surface):
    start = text.find(surface)
    while start >= 0:
        yield start
        start = text.find(surface, start + 1)


def run(model_name, api, phrasing, data, out_path, seed=0, prompts=None):
    prompts = prompts or PHRASINGS[phrasing]
    sentences = load_sentences(data)
    predict = {"gliner": predict_gliner, "gliner2": predict_gliner2}[api]
    spans, library = predict(model_name, [text for _, text in sentences], prompts, seed)

    prompt_to_label = {prompt: label for label, prompt in prompts.items()}
    documents = []
    for (identifier, text), found in zip(sentences, spans):
        documents.append({
            "id": identifier,
            "text": text,
            "spans": [{**span, "prompt": span["label"],
                       "label": prompt_to_label.get(span["label"], span["label"])}
                      for span in found],
        })

    record = {
        "model": model_name,
        "revision": _revision(model_name),
        "api": api,
        "phrasing": phrasing,
        "prompts": prompts,
        "score_floor": FLOOR,
        "threshold": "not applied; filter the saved scores",
        "data": str(data),
        "sentences": len(documents),
        "spans_at_floor": sum(len(d["spans"]) for d in documents),
        "seed": seed,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "interpreter": sys.executable,
        "packages": library,
        "code": _git_commit(),
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps({"run": record, "documents": documents},
                                         indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def _git_commit():
    try:
        return subprocess.run(("git", "rev-parse", "HEAD"), capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


PET_SCOPE = ("Activity", "Activity Data", "Actor", "Condition Specification",
             "Further Specification", "XOR Gateway")
THRESHOLDS = [round(0.3 + 0.05 * i, 2) for i in range(9)]  # 0.30 .. 0.70


def sweep(data, span_files, thresholds=THRESHOLDS, scope=PET_SCOPE):
    """Every phrasing at every threshold, scored on dev with text2bpmn.eval_ner.

    The model is not run again: each file holds every span at or above the
    floor with its score, so a threshold is a filter.
    """
    from text2bpmn.eval_ner import assemble, load_pet, load_predictions

    sentences = len(load_pet(data))
    rows = []
    for path in span_files:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))["run"]
        for threshold in thresholds:
            predicted = load_predictions(path, sentences, threshold)
            scored = assemble(data, predicted, scope=scope, bootstrap=0,
                              model_name=f"{saved['model']} {saved['phrasing']}")
            rows.append({"model": saved["model"], "phrasing": saved["phrasing"],
                         "threshold": threshold,
                         "predicted_spans": scored["predicted_spans"],
                         "strict_micro_f1": scored["strict"]["micro"]["f1"],
                         "relaxed_micro_f1": scored["relaxed"]["micro"]["f1"],
                         "strict_precision": scored["strict"]["micro"]["precision"],
                         "strict_recall": scored["strict"]["micro"]["recall"]})
    return rows


def best(rows, by="strict_micro_f1"):
    """The winning configuration, ties broken towards the higher threshold so
    the chosen point is the least generous of the equals."""
    return max(rows, key=lambda r: (r[by], r["threshold"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model")
    ap.add_argument("--api", choices=("gliner", "gliner2"), default="gliner")
    ap.add_argument("--phrasing", choices=(*PHRASINGS, "parallel-probe"), default="terse")
    ap.add_argument("--data", required=True, help="a PET split (.json/.jsonl) or a .txt description")
    ap.add_argument("--out", help="where to write the spans and the run record")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sweep", nargs="+", metavar="SPANS.json",
                    help="score saved dev spans at every threshold instead of running a model")
    ap.add_argument("--threshold-range", nargs=3, type=float, metavar=("MIN", "MAX", "STEP"),
                    help="sweep this range instead of 0.30-0.70 in steps of 0.05. A fine-tuned "
                         "model is confident, and its best threshold sits above the range the "
                         "zero-shot sweep was specified over")
    args = ap.parse_args()

    if args.sweep:
        thresholds = THRESHOLDS
        if args.threshold_range:
            low, high, step = args.threshold_range
            count = int(round((high - low) / step)) + 1
            thresholds = [round(low + step * i, 2) for i in range(count)]
        rows = sweep(args.data, args.sweep, thresholds)
        print("| model | phrasing | threshold | spans | strict P | strict R | strict F1 | relaxed F1 |")
        print("|---|---|---|---|---|---|---|---|")
        for row in rows:
            print(f"| {row['model']} | {row['phrasing']} | {row['threshold']} | "
                  f"{row['predicted_spans']} | {row['strict_precision']} | "
                  f"{row['strict_recall']} | {row['strict_micro_f1']} | {row['relaxed_micro_f1']} |")
        winner = best(rows)
        print(f"\nbest on dev by strict micro F1: {winner}")
        if args.out:
            Path(args.out).write_text(json.dumps({"rows": rows, "best": winner}, indent=2),
                                      encoding="utf-8")
            print(f"✅ Wrote {args.out}")
        return

    if not args.model:
        ap.error("--model is required unless --sweep is given")
    prompts = PARALLEL_PROBE if args.phrasing == "parallel-probe" else None
    record = run(args.model, args.api, args.phrasing, args.data, args.out, args.seed, prompts)
    print(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"✅ Wrote {args.out}")


if __name__ == "__main__":
    main()
