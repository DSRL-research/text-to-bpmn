import glob
import json
from pathlib import Path

import pm4py
import pytest

from text2bpmn.generate import generate
from text2bpmn.load import load_extraction
from text2bpmn.structure import validate

REPO = Path(__file__).resolve().parents[2]


def extraction(elements, flows):
    return {"participants": [], "flows": [dict(zip(("source", "target", "name"), f)) for f in flows],
            "elements": [dict(zip(("id", "type", "name", "lane"), e)) for e in elements]}


def edges(p):
    return {(p.nodes[f.source].name or p.nodes[f.source].kind, p.nodes[f.target].name or p.nodes[f.target].kind, f.name)
            for f in p.flows}


START = ("StartEvent_1", "startEvent", "Start", "Main Process")
END = ("EndEvent_1", "endEvent", "End", "Main Process")


def test_reads_finder3_printed_dict(tmp_path):
    f = tmp_path / "out.json"
    f.write_text("{'structured_data': {'participants': {'Clerk'}, 'elements': "
                 "[{'id': 'StartEvent_1', 'name': 'Start', 'type': 'startEvent', 'lane': 'Clerk'}], "
                 "'flows': []}}")
    assert load_extraction(f)["participants"] == ["Clerk"]


def test_task_info_becomes_documentation_of_preceding_task():
    p = validate(extraction(
        [START, ("Activity_00000001", "task", "Checks order", "Clerk"),
         ("TASK_INFO_00000002", "task", "for completeness", "Clerk"),
         ("Activity_00000003", "task", "Ships order", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "TASK_INFO_00000002"),
         ("TASK_INFO_00000002", "Activity_00000003"), ("Activity_00000003", "EndEvent_1")]))
    assert p.nodes["Activity_00000001"].documentation == ["for completeness"]
    assert ("Checks order", "Ships order", "") in edges(p)
    assert "TASK_INFO_00000002" not in p.nodes


def test_promoted_activity_stays_task_and_branches_through_xor():
    p = validate(extraction(
        [START, ("Activity_00000001", "exclusiveGateway", "Checks stock", "Clerk"),
         ("Activity_00000002", "task", "Ships order", "Clerk"),
         ("Activity_00000003", "task", "Orders stock", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "Activity_00000002", "Yes"),
         ("Activity_00000001", "Activity_00000003", "No"),
         ("Activity_00000002", "EndEvent_1"), ("Activity_00000003", "EndEvent_1")]))
    assert p.nodes["Activity_00000001"].kind == "task"
    kinds = sorted(n.kind for n in p.nodes.values() if n.origin == "inserted")
    assert kinds == ["exclusiveGateway", "exclusiveGateway"]  # split after the check, join before end
    assert {("exclusiveGateway", "Ships order", "Yes"), ("exclusiveGateway", "Orders stock", "No")} <= edges(p)


def test_pass_through_condition_gateway_is_removed_keeping_condition():
    p = validate(extraction(
        [START, ("Activity_00000001", "task", "Checks order", "Clerk"),
         ("XOR Gateway_00000002", "exclusiveGateway", "If the order is urgent", "Clerk"),
         ("Activity_00000003", "task", "Ships order", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "XOR Gateway_00000002"),
         ("XOR Gateway_00000002", "Activity_00000003", "Yes"), ("Activity_00000003", "EndEvent_1")]))
    assert not any(n.kind == "exclusiveGateway" for n in p.nodes.values())
    assert ("Checks order", "Ships order", "If the order is urgent") in edges(p)


def test_a_decision_whose_outcomes_meet_at_an_empty_gateway_is_removed_too():
    """Defect 5 (PET doc-4.1, 2026-11-09): removing the later, empty gateway
    merged the decision's two outgoing flows into one, and the decision, which
    rule 5 had already looked at, was left as a pass-through; validation then
    refused the model."""
    p = validate(extraction(
        [START, ("Activity_00000001", "task", "Checks form", "Clerk"),
         ("XOR Gateway_00000002", "exclusiveGateway", "complete?", "Clerk"),
         ("XOR Gateway_00000003", "exclusiveGateway", "otherwise", "Clerk"),
         ("Activity_00000004", "task", "Files form", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "XOR Gateway_00000002"),
         ("XOR Gateway_00000002", "Activity_00000004", "yes"),
         ("XOR Gateway_00000002", "XOR Gateway_00000003", "no"),
         ("XOR Gateway_00000003", "Activity_00000004"), ("Activity_00000004", "EndEvent_1")]))
    assert not any(n.kind == "exclusiveGateway" for n in p.nodes.values())
    assert ("Checks form", "Files form", "complete?") in edges(p)


def test_a_gateway_left_one_in_one_out_by_a_dropped_loop_is_removed():
    """The same defect through the other path: bypassing a gateway that only
    leads back to its predecessor makes a self-loop, which add_flow drops."""
    p = validate(extraction(
        [START, ("Activity_00000001", "task", "Checks form", "Clerk"),
         ("XOR Gateway_00000002", "exclusiveGateway", "complete?", "Clerk"),
         ("XOR Gateway_00000003", "exclusiveGateway", "again", "Clerk"),
         ("Activity_00000004", "task", "Files form", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "XOR Gateway_00000002"),
         ("XOR Gateway_00000002", "Activity_00000004", "yes"),
         ("XOR Gateway_00000002", "XOR Gateway_00000003", "no"),
         ("XOR Gateway_00000003", "XOR Gateway_00000002"), ("Activity_00000004", "EndEvent_1")]))
    assert not any(n.kind == "exclusiveGateway" for n in p.nodes.values())
    assert ("Checks form", "Files form", "complete?") in edges(p)


def test_unlabelled_branches_get_parallel_split_and_join():
    p = validate(extraction(
        [START, ("Activity_00000001", "task", "Receives order", "Clerk"),
         ("Activity_00000002", "task", "Packs goods", "Warehouse"),
         ("Activity_00000003", "task", "Prints invoice", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "Activity_00000002"),
         ("Activity_00000001", "Activity_00000003"),
         ("Activity_00000002", "EndEvent_1"), ("Activity_00000003", "EndEvent_1")]))
    kinds = sorted(n.kind for n in p.nodes.values() if n.origin == "inserted")
    assert kinds == ["parallelGateway", "parallelGateway"]


def test_extractor_metadata_becomes_task_documentation():
    x = extraction([START, ("Activity_00000001", "task", "Checks order", "Clerk"), END],
                   [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "EndEvent_1")])
    x["elements"][1]["metadata"] = ["for  completeness"]
    p = validate(x)
    assert p.nodes["Activity_00000001"].documentation == ["for completeness"]


def test_lane_name_variants_are_merged():
    p = validate(extraction(
        [START, ("Activity_00000001", "task", "Calls", "The patient"),
         ("Activity_00000002", "task", "Waits", "A patient"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "Activity_00000002"),
         ("Activity_00000002", "EndEvent_1")]))
    assert {n.lane for n in p.nodes.values()} == {"Patient"}
    # rule 7 reports what it did, like the other six (R2.17)
    lanes = [change for rule, change in p.log if rule == "lanes"]
    assert "lane 'The patient' -> 'Patient'" in lanes and "lane 'A patient' -> 'Patient'" in lanes
    assert "'Start' in 'Main Process', which holds no task -> 'Patient'" in lanes


SAVED_OUTPUTS = sorted(f for f in glob.glob(str(REPO / "*.json"))
                       if not Path(f).name.startswith("pet_") and "structured_data" in Path(f).read_text()[:40])


# ids as a list, so that with no saved outputs in the root (the release has none) the
# empty parameter set is skipped instead of failing collection
@pytest.mark.parametrize("path", SAVED_OUTPUTS, ids=[Path(p).name for p in SAVED_OUTPUTS])
def test_saved_finder3_outputs_give_valid_deterministic_bpmn(path, tmp_path):
    xml, report = generate(path)  # validate() raises if any structural problem remains
    assert generate(path)[0] == xml
    out = tmp_path / "out.bpmn"
    out.write_text(xml)
    graph = pm4py.read_bpmn(str(out))
    assert len(graph.get_flows()) == report["output_counts"]["flows"]
    json.dumps(report)


def test_render_draws_every_element_of_a_generated_diagram(tmp_path):
    import xml.etree.ElementTree as ET

    from text2bpmn.render import render

    bpmn = tmp_path / "diagram.bpmn"
    xml, _ = generate(REPO / "runs/final-3/cases/loan/extraction.json")  # the release run's loan extraction
    bpmn.write_text(xml)
    svg = ET.fromstring(render(bpmn))  # well-formed SVG

    B = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
    source = ET.fromstring(xml)
    tasks = [e.get("name") for e in source.iter(f"{B}task")]
    flows = len(list(source.iter(f"{B}sequenceFlow")))
    labels = " ".join(t.text or "" for t in svg.iter("{http://www.w3.org/2000/svg}text"))
    assert all(name.split()[0] in labels for name in tasks)
    assert len(list(svg.iter("{http://www.w3.org/2000/svg}polyline"))) == flows
    assert len(list(svg.iter("{http://www.w3.org/2000/svg}rect"))) >= len(tasks)


def test_both_outcomes_entering_a_parallel_split_are_joined_exclusively(tmp_path):
    """Rule 5 divided a gateway that merges and splits into a join and a split
    of the gateway's own type: here a parallel join waiting for both outcomes of
    a decision, of which only one is ever taken -- a deadlock WOFLAN reports."""
    from text2bpmn.bpmn_xml import to_xml
    x = extraction(
        [START, ("Activity_00000001", "task", "Receive order", "Clerk"),
         ("XOR Gateway_00000002", "exclusiveGateway", "If in stock", "Clerk"),
         ("Activity_00000003", "task", "Order stock", "Clerk"),
         ("ParallelGateway_split_00000004", "parallelGateway", "+", "Clerk"),
         ("Activity_00000005", "task", "Pack goods", "Clerk"), ("Activity_00000006", "task", "Print invoice", "Clerk"),
         ("ParallelGateway_join_00000007", "parallelGateway", "+", "Clerk"),
         ("Activity_00000008", "task", "Ship", "Clerk"), END],
        [("StartEvent_1", "Activity_00000001"), ("Activity_00000001", "XOR Gateway_00000002"),
         ("XOR Gateway_00000002", "ParallelGateway_split_00000004", "Yes"),
         ("XOR Gateway_00000002", "Activity_00000003", "No"),
         ("Activity_00000003", "ParallelGateway_split_00000004"),
         ("ParallelGateway_split_00000004", "Activity_00000005"), ("ParallelGateway_split_00000004", "Activity_00000006"),
         ("Activity_00000005", "ParallelGateway_join_00000007"), ("Activity_00000006", "ParallelGateway_join_00000007"),
         ("ParallelGateway_join_00000007", "Activity_00000008"), ("Activity_00000008", "EndEvent_1")])
    p = validate(x)
    inserted = [n for n in p.nodes.values() if n.origin == "inserted"]
    assert [(n.kind, len(p.incoming(n.id))) for n in inserted] == [("exclusiveGateway", 2)]
    path = tmp_path / "decision_into_parallel.bpmn"
    path.write_text(to_xml(p), encoding="utf-8")
    net, im, fm = pm4py.convert_to_petri_net(pm4py.read_bpmn(str(path)))
    sound, _ = pm4py.check_soundness(net, im, fm)
    assert sound


def test_a_decision_inside_a_parallel_branch_keeps_both_joins_right(tmp_path):
    """The decision's outcomes rejoin exclusively; the parallel branches, one of
    which holds that decision, rejoin in parallel. Typing a join by the first
    split on each path made the second exclusive: an AND split merged by an XOR
    join, which WOFLAN reports unsound."""
    from text2bpmn.bpmn_xml import to_xml
    tasks = [(f"Activity_0000000{i}", "task", name, "Clerk") for i, name in
             enumerate(["Receive", "Check", "Ship", "Store", "Archive", "Bill", "Close"])]
    x = extraction(
        [START, *tasks, ("XOR Gateway_00000009", "exclusiveGateway", "If in stock", "Clerk"), END],
        [("StartEvent_1", "Activity_00000000"),
         ("Activity_00000000", "Activity_00000001"), ("Activity_00000000", "Activity_00000005"),
         ("Activity_00000001", "XOR Gateway_00000009"),
         ("XOR Gateway_00000009", "Activity_00000002", "Yes"), ("XOR Gateway_00000009", "Activity_00000003", "No"),
         ("Activity_00000002", "Activity_00000004"), ("Activity_00000003", "Activity_00000004"),
         ("Activity_00000004", "Activity_00000006"), ("Activity_00000005", "Activity_00000006"),
         ("Activity_00000006", "EndEvent_1")])
    p = validate(x)
    joins = {p.nodes[p.outgoing(n.id)[0].target].name: n.kind
             for n in p.nodes.values() if n.origin == "inserted" and len(p.incoming(n.id)) >= 2}
    assert joins == {"Archive": "exclusiveGateway", "Close": "parallelGateway"}
    path = tmp_path / "nested.bpmn"
    path.write_text(to_xml(p), encoding="utf-8")
    net, im, fm = pm4py.convert_to_petri_net(pm4py.read_bpmn(str(path)))
    assert pm4py.check_soundness(net, im, fm)[0]
