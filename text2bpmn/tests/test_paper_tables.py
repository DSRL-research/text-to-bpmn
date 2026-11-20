"""The paper's tables rebuilt from the committed runs, against the numbers the drafts print."""
import json
from pathlib import Path

import pytest

from text2bpmn import paper_tables as pt

REPO = Path(__file__).resolve().parents[2]
NEUBERGER = REPO / "text2bpmn/baselines/neuberger"


@pytest.fixture(autouse=True)
def at_the_root(monkeypatch):
    monkeypatch.chdir(REPO)


def test_numbers_are_compared_as_printed():
    assert pt.same("1,300", "1300") and pt.same(".769 (5/1/2)", "0.769 (5/1/2)")
    assert pt.same("−0.036 [−0.063, −0.003]", "-0.036 [-0.063, -0.003]")
    assert pt.same("-", "-") and not pt.same("-", "0.000")
    assert not pt.same("5 of 10", "5 of 10 (+1)")
    assert not pt.same("0.186", "0.186 [0.126, 0.248]")


def test_a_number_that_differs_from_the_draft_is_reported():
    table = {"columns": ["", "a", "b"], "rows": [["x", "0.762", "45/45"]], "text": {}}
    pt.PAPER[99] = {"rows": [["x", "0.762", "44/45"]]}
    try:
        assert pt.compare_with_draft(99, table) == [("x", "b", "44/45", "45/45", None)]
    finally:
        del pt.PAPER[99]


def test_every_table_with_measurements_has_the_draft_numbers_and_a_builder():
    assert set(pt.BUILDERS) == set(pt.PAPER) == set(range(2, 11))
    for number, paper in pt.PAPER.items():
        widths = {len(row) for row in paper["rows"]}
        assert len(widths) == 1, f"Table {number}: rows of different lengths"


def expect(number, known=()):
    table = pt.build(number)
    assert pt.unexplained(table) == []
    assert sorted((d[0], d[1]) for d in table["differences"]) == sorted(known)
    assert all(v is not False for v in _flat(table.get("checks", {})))
    return table


def _flat(checks):
    return [v for v in checks.values() if isinstance(v, bool)]


def test_table_2_entity_distribution():
    expect(2)


def test_tables_3_and_4_entity_recognition():
    expect(3)
    expect(4)


def test_table_6_the_pairwise_classifier_on_302_pairs():
    expect(6)


def test_table_7_lanes_two_shares_the_draft_double_rounded():
    table = expect(7, [("Tasks in Main Process", "BERT, without"), ("Tasks in Main Process", "GLiNER, with FastCoref")])
    assert table["rows"][-1][1:] == ["5.1%", "5.0%", "4.2%"]


def test_table_10_reference_processes():
    expect(10)


needs_neuberger = pytest.mark.skipif(not NEUBERGER.is_dir(),
                                     reason="PET as Neuberger et al. convert it: python3 -m text2bpmn.pet_strict --fetch")


@needs_neuberger
def test_table_5_strict_comparison():
    expect(5)


@needs_neuberger
def test_table_8_relation_stages():
    table = expect(8, [("This method", "Parallel pairs"),
                       ("pairwise, inserted gateways collapsed (strict, pooled)", "text")])
    assert [row[-1] for row in table["rows"]] == ["45/45", "40/45", "45/45", "45/45"]


@needs_neuberger
def test_table_9_decisions():
    expect(9)


def test_the_lane_scores_can_be_written_away_from_the_run(tmp_path):
    from text2bpmn.lane_accuracy import score

    score("runs/final-3/coref_ablation", out=tmp_path)
    assert json.loads((tmp_path / "lane_scores.json").read_text()) == \
        json.loads(Path("runs/final-3/coref_ablation/lane_scores.json").read_text())


def test_a_paired_lane_difference_of_an_arm_with_itself_is_zero():
    from text2bpmn.compare_gliner_arm import paired_difference

    rows = json.loads(Path("runs/final-3/coref_ablation/lane_scores.json").read_text())["with_coref"]["rows"]
    difference, bootstrap = paired_difference(rows, rows)
    assert difference["of_gold"] == {"difference": 0.0, "ci95": [0.0, 0.0]} and bootstrap["documents"] == 43
    with pytest.raises(SystemExit):
        paired_difference(rows, rows[1:])


def test_the_loan_decision_question_is_rebuilt_as_the_run_sent_it():
    from text2bpmn import decisions
    from text2bpmn.checks.decision_prompt import analyse

    r = analyse("loan", 2)
    assert r["logged"]["label"] == "yes no no" and r["answer"] == {"step_1": "yes", "step_2": "no", "step_3": "no"}
    assert r["system_message"] == decisions.INSTRUCTIONS_SAME and r["worked_examples"] == 3
    assert r["user_message"].splitlines()[1:] == ["Decision [D]: If the applicant is not eligible", "Marked:",
                                                  "[1] Rejected the application (A loan officer)",
                                                  "[2] Prepared the acceptance pack (A loan officer)",
                                                  "[3] Sent (A loan officer)"]
