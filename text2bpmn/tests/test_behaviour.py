"""Behavioural footprints: what the models permit, not what they contain."""
import pytest

from text2bpmn.behaviour import _key, compare_behaviour, footprints, relabel
from text2bpmn.tests.test_compare import model


def test_a_label_is_matched_without_its_whitespace():
    """pm4py reads a multi-line label as "offersfrom logisticcompanies" and
    compare.py as single spaces, so neither spelling can be matched on."""
    assert _key("Get 3 offers\nfrom logistic\ncompanies") == _key("Get 3 offers from logistic companies")
    assert _key("Insure parcel") != _key("Insure parcels")


def test_footprints_report_what_can_follow_what(tmp_path):
    path = tmp_path / "linear.bpmn"
    model(["Check credit history", "Approve loan"], path=path)
    found = footprints(path)
    assert ("Check credit history", "Approve loan") in found["sequence"]
    assert found["parallel"] == set()
    assert found["activities"] == {"Check credit history", "Approve loan"}


def test_a_parallel_gateway_makes_its_branches_concurrent(tmp_path):
    path = tmp_path / "parallel.bpmn"
    model(["Check credit history", "Appraise property", "Assess risk"],
          gateway="parallelGateway", path=path)
    found = footprints(path)
    assert {"Appraise property", "Assess risk"} <= found["activities"]
    assert ("Appraise property", "Assess risk") in found["parallel"] or \
           ("Assess risk", "Appraise property") in found["parallel"]


def test_relabelling_renames_both_sides_of_a_pair():
    found = {"sequence": {("a", "b")}, "parallel": set(), "activities": {"a", "b"},
             "start_activities": {"a"}}
    assert relabel(found, {"a": "A"}) == {"sequence": {("A", "b")}, "parallel": set(),
                                          "activities": {"A", "b"}, "start_activities": {"A"}}


def test_a_model_compared_with_itself_is_behaviourally_identical(tmp_path):
    path = tmp_path / "same.bpmn"
    model(["Check credit history", "Approve loan", "Reject loan"],
          gateway="exclusiveGateway", path=path)
    result = compare_behaviour(path, path)
    assert result["behavioural_similarity"] == 1.0
    assert result["missing_behaviour"] == []


def test_different_wording_with_the_same_behaviour_scores_fully(tmp_path):
    """The point of relabelling: pm4py's own measure compares labels, so it
    cannot tell this model from an unrelated one."""
    reference = tmp_path / "ref.bpmn"
    generated = tmp_path / "gen.bpmn"
    model(["Check credit history", "Approve loan"], path=reference)
    model(["Credit history check", "Approve the loan"], path=generated)
    result = compare_behaviour(reference, generated)
    assert result["renamed"] == 2
    assert result["behavioural_similarity"] == 1.0
    assert result["pm4py_behavioral_similarity"] != 1.0


def test_a_missing_ordering_is_named(tmp_path):
    reference = tmp_path / "ref.bpmn"
    generated = tmp_path / "gen.bpmn"
    model(["Check credit history", "Appraise property", "Approve loan"], path=reference)
    model(["Check credit history", "Appraise property", "Approve loan"],
          gateway="parallelGateway", path=generated)
    result = compare_behaviour(reference, generated)
    assert result["relations"]["sequence"]["fn"] >= 1
