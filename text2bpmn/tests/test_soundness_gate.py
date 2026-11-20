"""The soundness check, the Validation Layer's typing of a merging gateway, and
the gate of relation idea 3 (text2bpmn/soundness_gate.py, decisions.gated)."""
import pytest

from text2bpmn import decisions, soundness_gate
from text2bpmn.bpmn_xml import to_xml
from text2bpmn.soundness_gate import check, graph_of, graph_of_bpmn, verdict
from text2bpmn.structure import validate
from text2bpmn.tests.test_decisions import node


def graph(kinds, flows):
    return kinds, [(f"f{i}", s, t) for i, (s, t) in enumerate(flows)]


START_END = {"s": "startEvent", "e": "endEvent"}


def test_a_sequence_and_matched_blocks_are_sound():
    assert check(*graph({**START_END, "a": "task"}, [("s", "a"), ("a", "e")]))["sound"]
    for kind in ("exclusiveGateway", "parallelGateway"):
        model = graph({**START_END, "x": kind, "a": "task", "b": "task", "j": kind},
                      [("s", "x"), ("x", "a"), ("x", "b"), ("a", "j"), ("b", "j"), ("j", "e")])
        assert check(*model)["sound"], kind


def test_parallel_lines_merged_exclusively_leave_a_token_behind():
    model = graph({**START_END, "x": "parallelGateway", "a": "task", "b": "task", "j": "exclusiveGateway"},
                  [("s", "x"), ("x", "a"), ("x", "b"), ("a", "j"), ("b", "j"), ("j", "e")])
    found = check(*model)
    assert found["sound"] is False and "proper completion" in found["reason"]


def test_a_choice_joined_in_parallel_deadlocks():
    model = graph({**START_END, "x": "exclusiveGateway", "a": "task", "b": "task", "j": "parallelGateway"},
                  [("s", "x"), ("x", "a"), ("x", "b"), ("a", "j"), ("b", "j"), ("j", "e")])
    found = check(*model)
    assert found["sound"] is False and "end is never reached" in found["reason"]


def test_an_element_that_never_fires_is_dead():
    model = graph({**START_END, "a": "task", "b": "task"}, [("s", "a"), ("a", "e"), ("b", "e")])
    found = check(*model)
    assert found["sound"] is False and "dead" in found["reason"]


def lines_meeting_at_a_decision_word():
    """Two parallel lines meeting at a decision word left without branches: the
    goods dispatch shape of 2026-11-12."""
    element = lambda i, kind: {"id": i, "name": i, "type": kind, "lane": "L"}  # noqa: E731
    flow = lambda s, t: {"source": s, "target": t}  # noqa: E731
    return {"participants": ["L"],
            "elements": [element("StartEvent_1", "startEvent"), element("Activity_00000001", "task"),
                         element("AND_Gateway_00000002", "parallelGateway"), element("Activity_00000003", "task"),
                         element("Activity_00000004", "task"), element("XOR_Gateway_00000005", "exclusiveGateway"),
                         element("Activity_00000006", "task"), element("EndEvent_1", "endEvent")],
            "flows": [flow("StartEvent_1", "Activity_00000001"), flow("Activity_00000001", "AND_Gateway_00000002"),
                      flow("AND_Gateway_00000002", "Activity_00000003"),
                      flow("AND_Gateway_00000002", "Activity_00000004"),
                      flow("Activity_00000003", "XOR_Gateway_00000005"),
                      flow("Activity_00000004", "XOR_Gateway_00000005"),
                      flow("XOR_Gateway_00000005", "Activity_00000006"), flow("Activity_00000006", "EndEvent_1")]}


def test_a_gateway_that_only_merges_takes_the_type_of_the_split_its_branches_part_at():
    process = validate(lines_meeting_at_a_decision_word())
    assert process.nodes["XOR_Gateway_00000005"].kind == "parallelGateway"
    assert check(*graph_of(process))["sound"]


def test_the_file_and_the_process_give_the_same_verdict(tmp_path):
    process = validate(lines_meeting_at_a_decision_word())
    path = tmp_path / "model.bpmn"
    path.write_text(to_xml(process, "m"), encoding="utf-8")
    assert check(*graph_of_bpmn(path)) == check(*graph_of(process))


def chain_with_a_block():
    """Nodes, plans and blocks for a: a decision with one branch, then a parallel block."""
    nodes = [node("exclusiveGateway", "g"), node("task", "a"), node("task", "b"), node("task", "c"),
             node("task", "d")]
    plans = {0: decisions._decision_plan([("Yes", "TRUE_BRANCH", [1])], [], 2)}
    blocks = {2: {"gateway": {"id": "p", "name": "meanwhile", "type": "parallelGateway", "lane": "Main Process"},
                  "lines": [[2], [3]], "goes_on": 4}}
    return nodes, {"Main Process"}, plans, blocks


def test_the_gate_leaves_a_sound_model_as_it_is():
    nodes, participants, plans, blocks = chain_with_a_block()
    data = decisions.assemble(nodes, participants, plans, blocks)
    gated = decisions.gated(nodes, participants, plans, blocks, dict(data))
    assert gated["soundness_gate"] == {"sound": True, "as_built": verdict(data), "undone": []}
    assert gated["flows"] == data["flows"] and gated["elements"] == data["elements"]


def test_the_gate_undoes_the_block_first_and_then_the_branches(monkeypatch):
    nodes, participants, plans, blocks = chain_with_a_block()
    calls = []

    def fake(data):  # unsound while anything but the text order is left
        calls.append(len(data["flows"]))
        branched = any(f.get("relation") in ("TRUE_BRANCH", "FALSE_BRANCH") for f in data["flows"])
        parallel = any(e["type"] == "parallelGateway" for e in data["elements"])
        return {"sound": not (branched or parallel), "reason": "test", "states": 0}

    monkeypatch.setattr(soundness_gate, "verdict", fake)
    data = decisions.gated(nodes, participants, plans, blocks, decisions.assemble(nodes, participants, plans, blocks))
    assert data["soundness_gate"]["undone"] == [{"parallel block": "meanwhile"}, {"decision": "g"}]
    assert data["soundness_gate"]["sound"] is True
    assert data == {**decisions.assemble(nodes, participants, {}, {}), "soundness_gate": data["soundness_gate"]}
    assert len(calls) == 3


def test_a_model_the_layer_refuses_is_not_sound(monkeypatch):
    import text2bpmn.structure

    def refuse(data):
        raise ValueError("left structural problems")

    monkeypatch.setattr(text2bpmn.structure, "validate", refuse)
    found = verdict(lines_meeting_at_a_decision_word())
    assert found["sound"] is False and "refused" in found["reason"]


@pytest.mark.parametrize("limit", [1])
def test_past_the_limit_the_verdict_is_unknown(limit):
    model = graph({**START_END, "x": "parallelGateway", "a": "task", "b": "task", "j": "parallelGateway"},
                  [("s", "x"), ("x", "a"), ("x", "b"), ("a", "j"), ("b", "j"), ("j", "e")])
    assert check(*model, limit=limit)["sound"] is None


def test_an_unsound_process_is_judged_not_crashed_on():
    # the gate meets in-pipeline models through graph_of: parallel lines merged
    # exclusively, built without the Validation Layer that now prevents it
    from text2bpmn.structure import Flow, Node, Process
    p = Process()
    for i, kind in (("s", "startEvent"), ("x", "parallelGateway"), ("a", "task"), ("b", "task"),
                    ("j", "exclusiveGateway"), ("e", "endEvent")):
        p.nodes[i] = Node(i, kind)
    p.flows = [Flow(s, t) for s, t in (("s", "x"), ("x", "a"), ("x", "b"), ("a", "j"), ("b", "j"), ("j", "e"))]
    found = check(*graph_of(p))
    assert found["sound"] is False and "proper completion" in found["reason"]
