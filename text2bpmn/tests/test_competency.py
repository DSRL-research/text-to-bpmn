"""The competency questions: what the graph answers that the diagram cannot."""
from pathlib import Path

import pytest

from text2bpmn.competency import QUESTIONS, ask, load
from text2bpmn.ontology import populate
from text2bpmn.tests.test_ontology import ONTOLOGY, PROCESS

pytestmark = pytest.mark.skipif(not ONTOLOGY.exists(), reason="ontology file not present")


@pytest.fixture(scope="module")
def answers(tmp_path_factory):
    out = tmp_path_factory.mktemp("competency") / "process.owl"
    populate(PROCESS, ONTOLOGY, out)
    graph, _ = load(out)
    return {result["question"]: result["rows"] for result in ask(graph)}


def question(index):
    return QUESTIONS[index][0]


def test_every_question_is_answered_in_order(answers):
    assert list(answers) == [q for q, _, _ in QUESTIONS]


def test_the_performer_of_each_activity(answers):
    assert sorted(map(tuple, answers[question(0)])) == [
        ("Cancel the order", "Manager"),
        ("Check the order", "Clerk"),
        ("Ship the order", "Manager"),
    ]


def test_the_alternative_branch_is_identified(answers):
    """Only possible because the flow keeps the relation it came from."""
    assert [tuple(row) for row in answers[question(4)]] == \
           [("If the order is urgent", "Cancel the order")]


def test_a_decision_with_both_branches_is_not_reported_as_faulty(answers):
    assert answers[question(5)] == []


def test_handover_between_actors_crosses_the_decision(answers):
    """The clerk's check leads, through the gateway, to the manager's work."""
    assert [tuple(row) for row in answers[question(6)]] == [("Clerk", "Manager", "2")]


def test_a_model_without_concurrency_answers_nothing(answers):
    assert answers[question(2)] == []


def _rows(process, path):
    populate(process, ONTOLOGY, path)
    graph, _ = load(path)
    return {result["question"]: result["rows"] for result in ask(graph)}


def test_a_decision_whose_branches_are_both_true_is_reported(tmp_path):
    """Two outgoing branches and no alternative among them: a fault the picture
    does not show, because both edges look the same."""
    both_true = {**PROCESS, "flows": [{**f, "relation": "TRUE_BRANCH", "name": "Yes"}
                                      if f["relation"] == "FALSE_BRANCH" else f
                                      for f in PROCESS["flows"]]}
    rows = _rows(both_true, tmp_path / "both_true.owl")
    assert [tuple(row) for row in rows[question(5)]] == [("If the order is urgent",)]


def test_a_decision_with_one_branch_is_removed_before_it_can_be_asked_about(tmp_path):
    """The Validation Layer bypasses a decision that has a single outgoing
    flow, so the question has nothing to report rather than reporting a fault
    the generated diagram does not contain."""
    one_sided = {**PROCESS,
                 "flows": [f for f in PROCESS["flows"] if f["relation"] != "FALSE_BRANCH"]}
    rows = _rows(one_sided, tmp_path / "one_sided.owl")
    assert rows[question(5)] == []
    assert "If the order is urgent" not in [row[0] for row in rows[question(3)]]


def test_an_extraction_can_be_queried_directly(tmp_path):
    """A .json extraction is populated into an ontology first, so the questions
    can be asked without running the pipeline again."""
    import json
    path = tmp_path / "extraction.json"
    path.write_text(json.dumps({"structured_data": PROCESS}), encoding="utf-8")
    graph, source = load(path)
    assert source.suffix == ".owl"
    assert any(result["rows"] for result in ask(graph))
