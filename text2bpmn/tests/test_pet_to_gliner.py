"""The PET to GLiNER conversion must be exactly reversible."""
from pathlib import Path

import pytest

from text2bpmn.eval_ner import load_pet, spans_from_bio
from text2bpmn.pet_to_gliner import (convert, round_trip_failures, to_char_spans,
                                     to_gliner, token_starts)

REPO = Path(__file__).resolve().parents[2]
SPLITS = ["pet_test.json", "pet_train.json",
          "text2bpmn/baselines/dev_split.json",
          "process-visualizer/src/token_classification_alex/final_train.jsonl"]

TOKENS = ["The", "financial", "officer", "checks", "the", "credit", "history"]
TAGS = ["B-Actor", "I-Actor", "I-Actor", "B-Activity", "B-Activity Data",
        "I-Activity Data", "I-Activity Data"]


def test_token_indices_include_the_last_token():
    example = to_gliner(TOKENS, TAGS)
    assert example["ner"] == [[0, 2, "Actor"], [3, 3, "Activity"], [4, 6, "Activity Data"]]
    assert example["tokenized_text"] == TOKENS


def test_a_single_token_span_is_a_pair_of_equal_indices():
    assert to_gliner(["x", "y"], ["O", "B-Activity"])["ner"] == [[1, 1, "Activity"]]


def test_adjacent_spans_of_the_same_label_stay_separate():
    """Two B- tags in a row are two entities, not one of double length."""
    assert to_gliner(["a", "b"], ["B-Actor", "B-Actor"])["ner"] == \
           [[0, 0, "Actor"], [1, 1, "Actor"]]


def test_token_starts_follow_the_single_space_join():
    assert token_starts(["ab", "c", "def"]) == [0, 3, 5]
    assert " ".join(["ab", "c", "def"])[5:8] == "def"


def test_the_inverse_recovers_the_character_spans():
    text, expected = spans_from_bio(TOKENS, TAGS)
    recovered = to_char_spans(to_gliner(TOKENS, TAGS))
    assert [(s["start"], s["end"], s["label"]) for s in recovered] == \
           [(s["start"], s["end"], s["label"]) for s in expected]
    assert [text[s["start"]:s["end"]] for s in recovered] == \
           ["The financial officer", "checks", "the credit history"]


@pytest.mark.parametrize("split", SPLITS)
def test_every_split_round_trips_without_losing_a_span(split):
    """The gate: if one span moves, the comparison is corrupt at the data layer."""
    path = REPO / split
    if not path.exists():
        pytest.skip(f"{split} not present")
    assert round_trip_failures(path) == []


@pytest.mark.parametrize("split", SPLITS)
def test_the_conversion_keeps_every_span_and_sentence(split):
    path = REPO / split
    if not path.exists():
        pytest.skip(f"{split} not present")
    gold = load_pet(path)
    examples = convert(path)
    assert len(examples) == len(gold)
    assert sum(len(e["ner"]) for e in examples) == sum(len(g[1]) for g in gold)
