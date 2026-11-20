import re

import pytest

from text2bpmn.finder3 import BPMNHybridExtractor


class StubCoref:
    """Stands in for FastCoref: returns the clusters it was given, as spans."""

    def __init__(self, *clusters, fail=False):
        self.clusters, self.fail = clusters, fail

    def predict(self, texts):
        if self.fail:
            raise RuntimeError("model unavailable")
        text = texts[0]

        def find(mention, start):  # whole words, so "he" does not match inside "The"
            match = re.compile(rf"\b{re.escape(mention)}\b").search(text, start)
            return (match.start(), match.end())

        spans = []
        for cluster in self.clusters:
            found, position = [], 0
            for mention in cluster:
                span = find(mention, position)
                found.append(span)
                position = span[1]
            spans.append(found)
        return [type("R", (), {"get_clusters": lambda self, as_strings=False: spans})()]


def resolve(text, *clusters, fail=False):
    x = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    x.coref_model = StubCoref(*clusters, fail=fail)
    return x._resolve_coreferences(text)


def test_pronoun_is_replaced_by_what_it_refers_to():
    text = "The Manager reviews the claim. Then he approves it."
    assert resolve(text, ["The Manager", "he"]) == "The Manager reviews the claim. Then The Manager approves it."


def test_possessive_pronoun_keeps_the_genitive():
    text = "The Clerk files the form. The Clerk signs his report."
    assert "The Clerk's report" in resolve(text, ["The Clerk", "his"])


def test_a_different_actor_is_never_renamed():
    """The failure this fixes: FastCoref grouped two distinct actors, and the
    original replaced one name with the other, moving activities between lanes."""
    text = "The Financial Officer performs the check. The Loan Officer assesses eligibility."
    assert resolve(text, ["The Financial Officer", "The Loan Officer"]) == text


def test_cluster_of_pronouns_only_is_left_alone():
    text = "They review it. They approve it."
    assert resolve(text, ["They", "They"]) == text


def test_text_survives_a_failing_coreference_model():
    text = "The Manager reviews the claim."
    assert resolve(text, ["The Manager"], fail=True) == text


@pytest.mark.parametrize("span, is_pronoun", [
    ("he", True), ("They", True), ("its", True), ("The Manager", False), ("", False), ("the applicant", False),
])
def test_pronoun_detection(span, is_pronoun):
    assert BPMNHybridExtractor._is_pronoun(span) is is_pronoun
