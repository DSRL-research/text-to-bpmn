"""The reference models are read with their lanes, flow names, inclusive
gateways and branch outcomes, ready to populate as they stand."""
import pytest

from text2bpmn.checks.reference_reader import read_reference


def kinds(model):
    out = {}
    for e in model["elements"]:
        out[e["type"]] = out.get(e["type"], 0) + 1
    return out


def test_the_loan_reference_is_read_whole():
    """The textbook's Solution 3.2: one pool, no lanes, no exclusive join."""
    model = read_reference("text2bpmn/cases/loan/reference.bpmn", "loan")
    assert kinds(model) == {"startEvent": 1, "task": 7, "parallelGateway": 2, "exclusiveGateway": 1, "endEvent": 2}
    assert not any(e["lane"] for e in model["elements"]) and model["participants"] == []
    outcomes = {f["name"]: f["relation"] for f in model["flows"] if f["name"]}
    assert outcomes == {"applicant eligible": "TRUE_BRANCH", "applicant not eligible": "FALSE_BRANCH"}


def test_lanes_are_read():
    """The authored loan model the release runs were scored against has four lanes."""
    model = read_reference("text2bpmn/cases/loan/reference_authored.bpmn", "loan")
    assert kinds(model) == {"startEvent": 1, "task": 7, "parallelGateway": 2, "exclusiveGateway": 2, "endEvent": 1}
    assert all(e["lane"] for e in model["elements"])
    assert model["participants"] == ["Financial Officer", "Loan Officer", "Property Appraiser", "System"]
    outcomes = {f["name"]: f["relation"] for f in model["flows"] if f["name"]}
    assert outcomes == {"eligible": "TRUE_BRANCH", "not eligible": "FALSE_BRANCH"}


def test_inclusive_gateways_are_kept():
    model = read_reference("text2bpmn/cases/goods_dispatch/reference.bpmn", "goods_dispatch")
    assert kinds(model)["inclusiveGateway"] == 2


def test_a_branch_name_missing_from_the_table_is_an_error(tmp_path):
    source = open("text2bpmn/cases/loan/reference.bpmn", encoding="utf-8").read()
    changed = source.replace('name="applicant not eligible"', 'name="perhaps"')
    assert changed != source
    (tmp_path / "x.bpmn").write_text(changed, encoding="utf-8")
    with pytest.raises(KeyError, match="perhaps"):
        read_reference(tmp_path / "x.bpmn", "loan")
