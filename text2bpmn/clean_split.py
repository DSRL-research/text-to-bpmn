"""The training pool without the development sentences: 315 to train on, 60 to
select on, the 42 of pet_test.json left for one final evaluation.

    python3 -m text2bpmn.clean_split            # writes text2bpmn/baselines/train_315.json

The 60 development sentences are the ones every GLiNER phrasing, threshold and
epoch was chosen on (`text2bpmn/baselines/dev_split_definition.json`). Until
2026-11-09 the fine-tuned models were nevertheless trained on all 375 sentences
of pet_train.json, those 60 included, so their selection was made on sentences
they had trained on. Training on this file instead keeps the development set
out of training, for BERT and GLiNER alike.

The development sentences are a random sample of sentences, not of documents,
so they share documents with the training sentences, as they always have.
"""
import argparse
import json
from pathlib import Path

POOL = "pet_train.json"
DEFINITION = "text2bpmn/baselines/dev_split_definition.json"
DEV = "text2bpmn/baselines/dev_split.json"
TEST = "pet_test.json"
OUT = "text2bpmn/baselines/train_315.json"


def split(pool=POOL, definition=DEFINITION, dev_path=DEV, test=TEST):
    """(training sentences, development sentences), each a list of PET records.

    Only the document names of the test split are read, to refuse any overlap;
    its sentences and labels are not.
    """
    records = json.loads(Path(pool).read_text(encoding="utf-8"))
    indices = set(json.loads(Path(definition).read_text(encoding="utf-8"))["indices"])
    train = [r for i, r in enumerate(records) if i not in indices]
    dev = [r for i, r in enumerate(records) if i in indices]
    if dev != json.loads(Path(dev_path).read_text(encoding="utf-8")):
        raise ValueError(f"{dev_path} is not the sentences {definition} names")
    test_documents = {r["document name"] for r in json.loads(Path(test).read_text(encoding="utf-8"))}
    shared = {r["document name"] for r in train + dev} & test_documents
    if shared:
        raise ValueError(f"training or development data shares documents with {test}: {sorted(shared)}")
    return train, dev


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    train, dev = split()
    Path(args.out).write_text(json.dumps(train, indent=2), encoding="utf-8")
    print(f"{len(train)} training sentences -> {args.out}; {len(dev)} development sentences held out")


if __name__ == "__main__":
    main()
