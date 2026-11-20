"""Convert a PET split to GLiNER's training format, reversibly.

    python3 -m text2bpmn.pet_to_gliner --data pet_train.json --out train.json

GLiNER trains on `{"tokenized_text": [...], "ner": [[first_token, last_token,
label], ...]}` with token indices that **include** the last token. PET gives
tokens with BIO tags, and text2bpmn/eval_ner.py scores character offsets into
the tokens joined by single spaces. Three index systems, so the conversion is
written with an inverse and tested by round trip: a silent off-by-one here would
corrupt the comparison at the data layer and read as a model result.

`to_char_spans` is that inverse. The test asserts that converting every sentence
of every split to token indices and back reproduces the character spans
`eval_ner.spans_from_bio` reads from the same sentence, span for span.
"""
import argparse
import json
from pathlib import Path

from text2bpmn.eval_ner import load_pet


def token_starts(tokens):
    """The character offset of each token in " ".join(tokens)."""
    starts, offset = [], 0
    for token in tokens:
        starts.append(offset)
        offset += len(token) + 1
    return starts


def to_gliner(tokens, tags):
    """One GLiNER training example: token indices, last token included."""
    ner, current = [], None
    for index, tag in enumerate(tags):
        if tag == "O":
            current = None
            continue
        prefix, _, label = tag.partition("-")
        if prefix == "B" or current is None or current[2] != label:
            current = [index, index, label]
            ner.append(current)
        else:
            current[1] = index
    return {"tokenized_text": list(tokens), "ner": [list(span) for span in ner]}


def to_char_spans(example):
    """The inverse: character spans into " ".join(tokenized_text)."""
    tokens = example["tokenized_text"]
    starts = token_starts(tokens)
    spans = []
    for first, last, label in example["ner"]:
        spans.append({"start": starts[first],
                      "end": starts[last] + len(tokens[last]),
                      "label": label, "score": 1.0})
    return spans


def convert(data_path):
    """Every sentence of a split as a GLiNER example."""
    return [to_gliner(tokens, tags) for _, _, tokens, tags in load_pet(data_path)]


def round_trip_failures(data_path):
    """Spans that do not survive the conversion, as (sentence, expected, got)."""
    failures = []
    for index, (text, gold_spans, tokens, tags) in enumerate(load_pet(data_path)):
        recovered = to_char_spans(to_gliner(tokens, tags))
        expected = [(s["start"], s["end"], s["label"]) for s in gold_spans]
        got = [(s["start"], s["end"], s["label"]) for s in recovered]
        if expected != got:
            failures.append((index, expected, got))
            continue
        # and the surface text of every span must be identical, byte for byte
        for span, back in zip(gold_spans, recovered):
            if text[span["start"]:span["end"]] != text[back["start"]:back["end"]]:
                failures.append((index, text[span["start"]:span["end"]],
                                 text[back["start"]:back["end"]]))
    return failures


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out")
    ap.add_argument("--labels", nargs="+", help="keep only these labels")
    args = ap.parse_args()

    failures = round_trip_failures(args.data)
    if failures:
        raise SystemExit(f"round trip lost {len(failures)} sentences' spans, "
                         f"first: {failures[0]}")
    examples = convert(args.data)
    if args.labels:
        keep = set(args.labels)
        examples = [{**e, "ner": [s for s in e["ner"] if s[2] in keep]} for e in examples]
    counts = {}
    for example in examples:
        for *_, label in example["ner"]:
            counts[label] = counts.get(label, 0) + 1
    print(f"{len(examples)} sentences, {sum(counts.values())} spans, round trip exact")
    print("spans per label:", dict(sorted(counts.items())))
    if args.out:
        Path(args.out).write_text(json.dumps(examples, ensure_ascii=False), encoding="utf-8")
        print(f"✅ Wrote {args.out}")


if __name__ == "__main__":
    main()
