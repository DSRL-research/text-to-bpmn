"""The span-based entity evaluator."""
import pytest

from text2bpmn.eval_ner import (bio_tags, entity_level, iou, match, spans_from_bio,
                                token_level)

TOKENS = ["The", "financial", "officer", "checks", "the", "credit", "history"]
TAGS = ["B-Actor", "I-Actor", "I-Actor", "B-Activity", "B-Activity Data",
        "I-Activity Data", "I-Activity Data"]


def test_gold_spans_carry_the_offsets_of_the_joined_text():
    text, spans = spans_from_bio(TOKENS, TAGS)
    assert text == "The financial officer checks the credit history"
    assert [(s["start"], s["end"], s["label"]) for s in spans] == [
        (0, 21, "Actor"), (22, 28, "Activity"), (29, 47, "Activity Data")]
    # the token list is what PET's own matching rule compares
    assert [s["tokens"] for s in spans] == [
        ["The", "financial", "officer"], ["checks"], ["the", "credit", "history"]]
    for span in spans:
        assert text[span["start"]:span["end"]]


def test_an_inside_tag_of_another_label_starts_a_span():
    """Dropping the annotation would be the alternative."""
    _, spans = spans_from_bio(["a", "b"], ["I-Actor", "I-Activity"])
    assert [s["label"] for s in spans] == ["Actor", "Activity"]


def test_iou_is_over_characters():
    assert iou({"start": 0, "end": 10}, {"start": 0, "end": 10}) == 1.0
    assert iou({"start": 0, "end": 10}, {"start": 5, "end": 15}) == pytest.approx(5 / 15)
    assert iou({"start": 0, "end": 5}, {"start": 6, "end": 10}) == 0.0


def test_one_prediction_cannot_satisfy_two_gold_spans():
    gold = [{"start": 0, "end": 10, "label": "Activity"},
            {"start": 0, "end": 12, "label": "Activity"}]
    predicted = [{"start": 0, "end": 11, "label": "Activity"}]
    assert len(match(gold, predicted, "relaxed")) == 1


def test_a_span_one_word_too_long_is_relaxed_but_not_strict():
    gold = [{"start": 0, "end": 21, "label": "Actor"}]
    predicted = [{"start": 0, "end": 28, "label": "Actor"}]
    assert match(gold, predicted, "strict") == []
    assert match(gold, predicted, "relaxed") == [(0, 0)]


def test_a_wrong_label_never_matches():
    gold = [{"start": 0, "end": 10, "label": "Actor"}]
    predicted = [{"start": 0, "end": 10, "label": "Activity"}]
    assert match(gold, predicted, "strict") == [] and match(gold, predicted, "relaxed") == []


def test_perfect_predictions_score_one():
    _, spans = spans_from_bio(TOKENS, TAGS)
    result = entity_level([(spans, [dict(s) for s in spans])], "strict")
    assert result["micro"]["f1"] == 1.0 and result["macro"]["f1"] == 1.0
    assert {label: scores["support"] for label, scores in result["per_label"].items()} == \
           {"Actor": 1, "Activity": 1, "Activity Data": 1}


def test_a_missed_label_is_a_false_negative_not_an_error():
    _, spans = spans_from_bio(TOKENS, TAGS)
    result = entity_level([(spans, [])], "strict")
    assert result["micro"] == {"tp": 0, "fp": 0, "fn": 3, "precision": 0.0,
                               "recall": 0.0, "f1": 0.0}


def test_tags_are_derived_back_from_spans():
    text, spans = spans_from_bio(TOKENS, TAGS)
    assert bio_tags(TOKENS, spans) == TAGS


def test_token_accuracy_separates_the_o_tags_from_the_entities():
    """The published accuracy counts every token, and most tokens are O."""
    gold = ["O"] * 8 + ["B-Activity", "I-Activity"]
    predicted = ["O"] * 8 + ["O", "O"]
    result = token_level([(gold, predicted)])
    assert result["accuracy"] == 0.8, "nothing found, and still 0.8"
    assert result["accuracy_on_entity_tokens"] == 0.0
    assert result["share_of_tokens_that_are_O"] == 0.8


def test_a_label_scope_fixes_what_is_averaged():
    """Every model is averaged over the same classes, whatever it predicts."""
    gold = [{"start": 0, "end": 5, "label": "Activity"},
            {"start": 6, "end": 9, "label": "Activity Data"}]
    predicted = [{"start": 0, "end": 5, "label": "Activity"},
                 {"start": 6, "end": 9, "label": "TASK_INFO"}]
    scoped = entity_level([(gold, predicted)], "strict", scope=["Activity", "Activity Data"])
    assert sorted(scoped["per_label"]) == ["Activity", "Activity Data"]
    # the out-of-scheme prediction is reported, not counted
    assert scoped["predictions_outside_the_scope"] == {"TASK_INFO": 1}
    assert scoped["micro"]["fp"] == 0 and scoped["micro"]["fn"] == 1
    widened = entity_level([(gold, predicted)], "strict",
                           scope=["Activity", "Activity Data", "TASK_INFO"])
    assert widened["micro"]["fp"] == 1, "counting it as an error is the stricter reading"


def test_restricting_the_scope_does_not_change_which_spans_matched():
    """Matching runs over every span; the scope only decides what is counted."""
    gold = [{"start": 0, "end": 10, "label": "Actor"}]
    predicted = [{"start": 0, "end": 10, "label": "Activity"}]
    narrow = entity_level([(gold, predicted)], "strict", scope=["Actor"])
    assert narrow["micro"]["fn"] == 1 and narrow["micro"]["fp"] == 0


def test_the_bootstrap_interval_brackets_the_point_estimate():
    from text2bpmn.eval_ner import bootstrap_micro_f1
    text = "The financial officer checks the credit history"
    documents = []
    for keep in (True, True, True, False, False):
        _, spans = spans_from_bio(TOKENS, TAGS)
        documents.append((spans, [dict(s) for s in spans] if keep else []))
    result = bootstrap_micro_f1(documents, "strict", resamples=200, seed=0)
    assert result["ci95_low"] <= result["point"] <= result["ci95_high"]
    assert result["resamples"] == 200 and result["sentences"] == 5


def test_the_bootstrap_is_reproducible_from_its_seed():
    from text2bpmn.eval_ner import bootstrap_micro_f1
    _, spans = spans_from_bio(TOKENS, TAGS)
    documents = [(spans, [dict(s) for s in spans]), (spans, [])]
    first = bootstrap_micro_f1(documents, "strict", resamples=100, seed=7)
    second = bootstrap_micro_f1(documents, "strict", resamples=100, seed=7)
    assert first == second
