"""Naming of the matched tasks: what the element counts do not measure."""
import pytest

from text2bpmn.labels import (content_words, head_word, label_metrics, pair_metrics,
                              shares_a_word)
from text2bpmn.tests.test_compare import model


def test_content_words_are_lemmatised_without_stopwords():
    assert content_words("Prepared the acceptance pack") == ("prepare", "acceptance", "pack")


def test_the_object_head_is_the_last_noun_phrase():
    assert head_word("Check the credit history") == "history"
    assert head_word("Develop new symptoms") == "symptom"


def test_an_identical_label_scores_perfectly():
    metrics = pair_metrics("Check credit history", "Check credit history")
    assert (metrics["lemma_jaccard"], metrics["content_recall"], metrics["head_kept"]) == (1.0, 1.0, True)


def test_a_truncated_label_loses_the_object_head():
    """The defect the case runs are full of: the activity's object never
    reached its label."""
    metrics = pair_metrics("Develop new symptoms", "Develops new")
    assert metrics["head_kept"] is False and metrics["head"] == "symptom"
    assert metrics["content_recall"] < 1.0


def test_a_longer_label_keeps_the_meaning_but_not_the_jaccard():
    """Content recall separates what was lost from what was merely added."""
    metrics = pair_metrics("Assess eligibility", "Assess the applicant's eligibility")
    assert metrics["content_recall"] == 1.0
    assert metrics["lemma_jaccard"] < 1.0


@pytest.mark.parametrize("first, second, shared", [
    ("Prescribe Treatment and Followups", "Sets up periodic follow-ups", True),  # hyphenation
    ("Clarify shipment method", "Clarifies who", True),  # the tagger's lemma
    ("Perform Evaluation", "Inform the", False),
])
def test_sharing_a_word_tolerates_hyphens_and_lemmas(first, second, shared):
    assert shares_a_word(set(content_words(first)), set(content_words(second))) is shared


def test_a_pair_matched_with_nothing_in_common_is_reported(tmp_path):
    """Two labels can match at the threshold on character similarity alone, and
    then count as a true positive while naming something else."""
    reference = model(["Perform Evaluation"], path=tmp_path / "ref.bpmn")
    generated = model(["Inform the"], path=tmp_path / "gen.bpmn")
    summary = label_metrics(reference, generated)["summary"]
    assert summary["matched"] == 1, "the matcher pairs them"
    assert summary["matched_without_a_shared_word"] == [("Perform Evaluation", "Inform the")]


def test_single_word_labels_are_listed(tmp_path):
    reference = model(["Send the acceptance pack"], path=tmp_path / "ref.bpmn")
    generated = model(["Sent"], path=tmp_path / "gen.bpmn")
    assert label_metrics(reference, generated)["summary"]["single_word_labels"] == ["Sent"]
