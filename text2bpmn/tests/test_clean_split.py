"""The 315/60 split the recognisers train and select on."""
import json

from text2bpmn.clean_split import OUT, split


def test_the_split_is_the_pool_minus_the_development_sentences():
    train, dev = split()
    assert (len(train), len(dev)) == (315, 60)
    key = lambda r: (r["document name"], r["sentence-ID"], tuple(r["tokens"]))
    assert not {key(r) for r in train} & {key(r) for r in dev}
    assert dev == json.load(open("text2bpmn/baselines/dev_split.json", encoding="utf-8"))


def test_the_committed_training_file_is_what_the_split_gives():
    train, _ = split()
    assert json.load(open(OUT, encoding="utf-8")) == train


def test_no_document_of_the_test_split_is_trained_or_selected_on():
    train, dev = split()
    test = {r["document name"] for r in json.load(open("pet_test.json", encoding="utf-8"))}
    assert not {r["document name"] for r in train + dev} & test
