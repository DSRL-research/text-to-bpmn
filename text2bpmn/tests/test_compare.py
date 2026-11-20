from pathlib import Path

import pytest

from text2bpmn.bpmn_xml import to_xml
from text2bpmn.compare import compare, read_bpmn, similarity
from text2bpmn.structure import Flow, Node, Process

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "text2bpmn" / "cases"


def model(tasks, gateway=None, path=None):
    """A small process: start -> tasks in order -> end, optionally splitting at a gateway."""
    p = Process()
    p.nodes["start"] = Node("start", "startEvent", "Start", "Lane", "test")
    for i, name in enumerate(tasks):
        p.nodes[f"t{i}"] = Node(f"t{i}", "task", name, "Lane", "test")
    p.nodes["end"] = Node("end", "endEvent", "End", "Lane", "test")
    if gateway:
        p.nodes["gw"] = Node("gw", gateway, "", "Lane", "test")
        p.flows = [Flow("start", "t0"), Flow("t0", "gw"), Flow("gw", "t1"), Flow("gw", "t2"),
                   Flow("t1", "end"), Flow("t2", "end")]
    else:
        ids = ["start"] + [f"t{i}" for i in range(len(tasks))] + ["end"]
        p.flows = [Flow(a, b) for a, b in zip(ids, ids[1:])]
    path.write_text(to_xml(p, "test"))
    return read_bpmn(path)


def test_identical_models_score_perfectly(tmp_path):
    m = model(["Check credit history", "Approve loan"], path=tmp_path / "a.bpmn")
    result = compare(m, m)
    for element in ("tasks", "gateways", "edges"):
        assert (result[element]["fp"], result[element]["fn"]) == (0, 0)
    assert result["ged"]["ged"] == 0 and result["ged"]["similarity"] == 1.0


def test_labels_match_despite_word_order_and_wording():
    assert similarity("Check credit history", "Credit history check") > 0.9
    assert similarity("Assess loan risk", "Risk assessment") > 0.7
    assert similarity("Prepare acceptance pack", "Approve loan application") < 0.5


def test_renamed_and_missing_tasks(tmp_path):
    reference = model(["Check credit history", "Approve loan"], path=tmp_path / "r.bpmn")
    generated = model(["Credit history check", "Send parcel"], path=tmp_path / "g.bpmn")
    tasks = compare(reference, generated)["tasks"]
    assert (tasks["tp"], tasks["fp"], tasks["fn"]) == (1, 1, 1)  # one renamed, one unrelated


def test_edges_follow_gateways_between_tasks(tmp_path):
    m = model(["Assess", "Approve", "Reject"], gateway="exclusiveGateway", path=tmp_path / "x.bpmn")
    names = {n.id: n.name for n in m.nodes.values()}
    assert {(names[s], names[t]) for s, t in m.task_edges()} == {("Assess", "Approve"), ("Assess", "Reject")}
    assert [(g.detail, g.role) for g in m.gateways] == [("XOR", "split")]


@pytest.mark.skipif(not (CASES / "loan" / "reference.bpmn").exists(), reason="case files missing")
def test_extra_generated_task_costs_a_false_positive():
    """The reviewer's question: the hand-made loan model behind Figure 11 of the
    submitted version has an extra task ("Reject automatically"), which the
    original evaluator absorbed into a mapping group, keeping precision at 1.000."""
    result = compare(read_bpmn(CASES / "loan" / "reference.bpmn"),
                     read_bpmn(CASES / "loan" / "published_generated.bpmn"))
    assert result["tasks"]["fp"] >= 1
    assert result["tasks"]["precision"] < 1.0
    assert "Reject automatically" in result["unmatched_generated"] + [g for _, g in result["mapping"]]
