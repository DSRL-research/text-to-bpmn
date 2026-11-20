from pathlib import Path

import pytest

from text2bpmn.guardrail_replay import PARTITIONS, partition, replay, replay_partitions
from text2bpmn.guardrails import false_branch_guardrail, has_marker, is_else_marker
from text2bpmn.relation_metrics import load_dataset, predictions_from_report

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode, e1, e2, expected", [
    ("entity_1", "Otherwise", "replies via email", "FALSE_BRANCH"),
    ("entity_1", "sends offer", "otherwise replies", "SEQUENCE"),
    ("entity_2", "Otherwise", "replies via email", "SEQUENCE"),  # legacy: misses the annotated form
    ("entity_2", "sends offer", "otherwise replies", "FALSE_BRANCH"),
    ("both", "If not", "waits", "FALSE_BRANCH"),
    ("off", "Otherwise", "replies via email", "SEQUENCE"),
])
def test_guardrail_modes(mode, e1, e2, expected):
    assert false_branch_guardrail("SEQUENCE", e1, e2, mode) == expected


@pytest.mark.parametrize("head, fires", [
    ("Otherwise", True),
    ("otherwise, rejects the application", True),
    ("Else reject them", True),
    ("Or else, the clerk archives it", True),
    ("If not,", True),
    ("If not", True),
    ("If not already registered", False),   # a new condition, not the branch of one
    ("asks someone else", False),
    ("elsewhere stores the file", False),
    ("rejects the claim otherwise", False),
])
def test_a_marker_must_open_the_head_mention(head, fires):
    assert has_marker(head) is fires
    assert false_branch_guardrail("SEQUENCE", head, "x") == ("FALSE_BRANCH" if fires else "SEQUENCE")


@pytest.mark.parametrize("span, merged", [
    ("Otherwise", True), ("Otherwise,", True), ("else:", True), ("Or else", True), ("If not,", True),
    ("Otherwise, if the amount is large", False),  # a new decision, not the else of the last one
    ("Otherwise rejects the application", False),
    ("If not already registered", False),
    ("In case of small amounts", False),
])
def test_only_a_bare_else_marker_merges_into_the_decision_before(span, merged):
    assert is_else_marker(span) is merged


def test_guardrail_only_rewrites_sequence():
    assert false_branch_guardrail("TRUE_BRANCH", "Otherwise", "x") == "TRUE_BRANCH"


def test_replay_refuses_when_legacy_guardrail_may_have_fired():
    samples = [{"entity_1": "a", "entity_2": "else b", "label": "FALSE_BRANCH"}]
    with pytest.raises(ValueError):
        replay(samples, ["FALSE_BRANCH"])


def test_stored_run_guardrail_effect_is_zero_in_every_mode():
    samples = load_dataset(REPO / "benchmark_silver_2.jsonl")
    results = replay(samples, predictions_from_report(REPO / "benchmark_results_silver_fewshot_final2.md", samples))
    assert {mode: r["fired"] for mode, r in results.items()} == {"entity_1": 0, "entity_2": 0, "both": 0, "off": 0}
    assert {r["metrics"]["correct"] for r in results.values()} == {274}


def test_stored_run_bert_baseline_gains_from_corrected_guardrail():
    samples = load_dataset(REPO / "benchmark_silver_2.jsonl")
    stored = predictions_from_report(REPO / "benchmark_results_silver_fewshot_final2.md", samples, "bert")
    results = replay(samples, stored)
    assert (results["entity_2"]["fired"], results["entity_2"]["metrics"]["correct"]) == (0, 129)
    assert (results["entity_1"]["fired"], results["entity_1"]["metrics"]["correct"]) == (25, 154)


def test_markers_partition_the_benchmark():
    samples = load_dataset(REPO / "benchmark_silver_2.jsonl")
    sizes = {which: len(partition(samples, which)) for which in PARTITIONS}
    assert sizes == {"all": 302, "with_marker": 46, "marker_free": 256}
    # every marker in this benchmark sits in a FALSE_BRANCH sample, so a rule that
    # fires on any marker cannot be punished here for firing too eagerly
    assert {samples[i]["label"] for i in partition(samples, "with_marker")} == {"FALSE_BRANCH"}
    assert sum(samples[i]["label"] == "FALSE_BRANCH"
               for i in partition(samples, "marker_free")) == 23


def test_without_a_marker_every_mode_is_identical():
    """The bound on what the rule can contribute: with no marker to fire on,
    the numbers are the model's own."""
    samples = load_dataset(REPO / "benchmark_silver_2.jsonl")
    for model in ("dspy", "bert"):
        stored = predictions_from_report(REPO / "benchmark_results_silver_fewshot_final2.md", samples, model)
        free = replay_partitions(samples, stored)["marker_free"]["modes"]
        assert {r["fired"] for r in free.values()} == {0}
        assert len({r["metrics"]["correct"] for r in free.values()}) == 1


def test_false_branch_recall_depends_on_the_marker():
    """Both models find the false branch mainly where the text says "otherwise"."""
    samples = load_dataset(REPO / "benchmark_silver_2.jsonl")
    def recall(model, which, mode):
        stored = predictions_from_report(REPO / "benchmark_results_silver_fewshot_final2.md", samples, model)
        block = replay_partitions(samples, stored)[which]["modes"][mode]
        return round(block["metrics"]["per_class"]["FALSE_BRANCH"]["recall"], 3)

    assert (recall("dspy", "with_marker", "entity_1"), recall("dspy", "marker_free", "entity_1")) == (0.978, 0.13)
    assert (recall("bert", "with_marker", "entity_1"), recall("bert", "marker_free", "entity_1")) == (0.891, 0.0)
