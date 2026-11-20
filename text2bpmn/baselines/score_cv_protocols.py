"""Score saved cross-validation predictions under both protocols.

    python3 text2bpmn/baselines/score_cv_protocols.py text2bpmn/baselines/cv/bert-pet-full

No model is run: each fold's predictions were saved when it trained, so the two
protocols score exactly the same outputs.

- **this project's**: one-to-one matching by optimal assignment, strict on
  character offsets and relaxed at character IoU >= 0.5, micro-averaged over
  every span in the fold.
- **PET's**, read from `petbenchmarks` 0.0.2: token lists equal, or equal after
  dropping up to one word from either end, scored per document and then averaged
  over documents, so a two-sentence document counts as much as a thirty-four
  sentence one.
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from text2bpmn.eval_ner import entity_level, pet_protocol

LABELS = ["Activity", "Activity Data", "Actor", "AND Gateway",
          "Condition Specification", "Further Specification", "XOR Gateway"]


def _with_tokens(rows, texts):
    """Predictions saved before spans carried token lists: recover them from the
    sentence each row came from, which is what PET's rule compares."""
    for row, text in zip(rows, texts):
        for span in row["gold"] + row["predicted"]:
            span.setdefault("tokens", text[span["start"]:span["end"]].split())
    return rows


def _fold_texts(directory, fold):
    """The sentences of one fold, in the order its predictions were written."""
    record = json.loads((directory / "cv.json").read_text(encoding="utf-8")) \
        if (directory / "cv.json").exists() else {}
    folds_file = record.get("folds_definition_file", "text2bpmn/baselines/cv_folds.json")
    records_file = record.get("records", "pet_train.json")
    indices = json.loads(Path(folds_file).read_text(encoding="utf-8"))["fold_sentence_indices"][fold]
    corpus = json.loads(Path(records_file).read_text(encoding="utf-8"))
    return [" ".join(corpus[i]["tokens"]) for i in indices]


def score(directory):
    directory = Path(directory)
    ours, theirs = [], []
    for path in sorted(directory.glob("predictions_fold*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        rows = _with_tokens(rows, _fold_texts(directory, int(path.stem[-1])))
        sentences = [(r["gold"], r["predicted"]) for r in rows]
        ours.append({
            "fold": path.stem,
            "strict": entity_level(sentences, "strict", scope=LABELS)["micro"]["f1"],
            "relaxed": entity_level(sentences, "relaxed", scope=LABELS)["micro"]["f1"],
        })
        by_document = defaultdict(lambda: ([], []))
        for row in rows:
            gold, predicted = by_document[row["document"]]
            gold.extend(row["gold"])
            predicted.extend(row["predicted"])
        pet = pet_protocol(list(by_document.values()), scope=LABELS)
        theirs.append({"fold": path.stem, "documents": pet["documents"],
                       "macro_f1": pet["macro"]["f1"],
                       "per_label": {l: s["f1"] for l, s in pet["per_label"].items()}})
    return ours, theirs


def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else "text2bpmn/baselines/cv/bert-pet-full"
    ours, theirs = score(directory)
    if not ours:
        raise SystemExit(f"no saved predictions in {directory}")

    print(f"# {Path(directory).name}, {len(ours)} folds\n")
    print("## This project's protocol (micro over spans)\n")
    print("| Fold | strict F1 | relaxed F1 |"); print("|---|---|---|")
    for row in ours:
        print(f"| {row['fold'][-1]} | {row['strict']} | {row['relaxed']} |")
    for key in ("strict", "relaxed"):
        values = [r[key] for r in ours]
        print(f"| **mean** | " + (f"**{statistics.mean(values):.3f} "
              f"+/- {statistics.stdev(values):.3f}**" if key == "strict" else "") +
              " | " + (f"**{statistics.mean(values):.3f} "
              f"+/- {statistics.stdev(values):.3f}**" if key == "relaxed" else "") + " |"
              if False else "", end="")
    strict = [r["strict"] for r in ours]; relaxed = [r["relaxed"] for r in ours]
    print(f"| **mean** | **{statistics.mean(strict):.3f} +/- {statistics.stdev(strict):.3f}** "
          f"| **{statistics.mean(relaxed):.3f} +/- {statistics.stdev(relaxed):.3f}** |")

    print("\n## PET's protocol (one-word relaxation, macro over documents)\n")
    labels = list(theirs[0]["per_label"])
    print("| Fold | documents | macro F1 | " + " | ".join(labels) + " |")
    print("|---" * (len(labels) + 3) + "|")
    for row in theirs:
        print(f"| {row['fold'][-1]} | {row['documents']} | {row['macro_f1']} | " +
              " | ".join(f"{row['per_label'][l]}" for l in labels) + " |")
    macro = [r["macro_f1"] for r in theirs]
    per_label_mean = {l: statistics.mean([r["per_label"][l] for r in theirs]) for l in labels}
    print(f"| **mean** | | **{statistics.mean(macro):.3f} "
          f"+/- {statistics.stdev(macro):.3f}** | " +
          " | ".join(f"{per_label_mean[l]:.3f}" for l in labels) + " |")

    out = Path("text2bpmn/results") / f"cv_protocols_{Path(directory).name}.json"
    out.write_text(json.dumps({"ours": ours, "pet": theirs}, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
