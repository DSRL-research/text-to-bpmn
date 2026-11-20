"""A fine-tuned GLiNER's spans on whole texts, read one sentence at a time.

    <GLiNER venv>/bin/python -m text2bpmn.gliner_spans --model DIR --texts IN.json --out OUT.json

Runs in GLiNER's own venv (it needs a newer transformers than the pipeline),
called by text2bpmn/run_gliner_arm.py. IN.json is {document id: text}, the
text exactly as the pipeline's recogniser would see it (coreference resolved,
whitespace normalised), so the character offsets written here are offsets in
that text and finder3 can take the spans as they are.

One sentence at a time, because that is how the model was trained and how it
was selected and scored: PET's sentences are its training, development and
test items. Given a whole document instead, its confidence collapses: on the
healthcare case at its development threshold of 0.85 it keeps 8 spans for the
whole text and 76 sentence by sentence (2026-11-10), which is why the
pipeline arm of 2026-10-05, an earlier run not in this repository, built
almost nothing there.

Every span at or above gliner_baseline.FLOOR is written with its score, so the
threshold is applied by the caller, as the development sweep applied it. With
GLiNER's flat decoding this keeps exactly the spans a run at the threshold
itself would return: a span above the threshold can only lose to an
overlapping span with a higher score.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from text2bpmn.gliner_baseline import FLOOR, TRAINED_LABELS, _versions

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentences(text):
    """(start, end) of each sentence of `text`: split where a full stop,
    question or exclamation mark is followed by whitespace, so "2.5" and
    "e.g.," stay whole; leading and trailing whitespace left out."""
    out, start = [], 0
    for boundary in list(SENTENCE_END.finditer(text)) + [None]:
        end = boundary.start() if boundary else len(text)
        piece = text[start:end]
        lead = len(piece) - len(piece.lstrip())
        if piece.strip():
            out.append((start + lead, start + lead + len(piece.strip())))
        if boundary:
            start = boundary.end()
    return out


def predict(model, text, floor=FLOOR):
    """Spans over the whole text, sentence by sentence, offsets in `text`;
    and how many sentences were longer than the model reads."""
    spans, too_long = [], 0
    limit = getattr(model.config, "max_len", None)
    for start, end in sentences(text):
        piece = text[start:end]
        if limit and len(piece.split()) > limit:
            too_long += 1
        for e in model.predict_entities(piece, TRAINED_LABELS, threshold=floor):
            spans.append({"start": start + int(e["start"]), "end": start + int(e["end"]),
                          "label": e["label"], "score": round(float(e["score"]), 4)})
    return spans, too_long


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--floor", type=float, default=FLOOR)
    args = ap.parse_args(argv)

    import torch
    from gliner import GLiNER

    torch.manual_seed(0)
    model = GLiNER.from_pretrained(args.model, load_tokenizer=True).eval()
    texts = json.loads(Path(args.texts).read_text(encoding="utf-8"))
    documents = {}
    for name, text in texts.items():
        spans, too_long = predict(model, text, args.floor)
        documents[name] = {"text": text, "spans": spans, "sentences": len(sentences(text)),
                           "sentences_longer_than_the_model_reads": too_long}
    weights = [p for p in Path(args.model).iterdir() if p.suffix in (".bin", ".safetensors")]
    record = {"model": args.model, "weights_sha256": {p.name: _sha256(p) for p in weights},
              "labels": TRAINED_LABELS, "floor": args.floor, "read": "one sentence at a time",
              "python": sys.version.split()[0],
              "versions": _versions(["gliner", "transformers", "tokenizers", "torch", "numpy"]),
              "documents": documents}
    Path(args.out).write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(documents)} texts, {sum(len(d['spans']) for d in documents.values())} spans "
          f"at or above {args.floor} -> {args.out}")


if __name__ == "__main__":
    main()
