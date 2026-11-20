"""The second PET measure of text2bpmn/pet_flow_eval.py: every flow shape."""
from text2bpmn.pet_flow_eval import ALL_SHAPES, SHAPES, score_all_flows


def span(label, start, kind, element=None):
    return {"entity_group": label, "start": start, "end": start + 1, "type": kind, "id": element}


def flow(source, target):
    return {"source": source, "target": target}


ELEMENTS = {i: {"id": i, "type": t} for i, t in
            (("g", "exclusiveGateway"), ("a", "task"), ("b", "task"), ("h", "exclusiveGateway"))}


def test_an_else_branch_counts_from_the_decision_its_marker_stands_for():
    # "If X, A. Otherwise, B.": the condition is folded, the else-marker aliased
    spans = [span("XOR Gateway", 0, "exclusiveGateway", "g"), span("Condition Specification", 3, "exclusiveGateway"),
             span("Activity", 6, "task", "a"), span("XOR Gateway", 9, "exclusiveGateway"),
             span("Activity", 20, "task", "b")]
    job = {"all_flows": [{"source": [3, 4], "target": [6, 7]},     # condition -> A
                         {"source": [9, 10], "target": [20, 21]},  # otherwise -> B, which the first measure drops
                         {"source": [0, 1], "target": [9, 10]}]}   # decision -> its own else-marker: no edge
    counts = score_all_flows(job, spans, ELEMENTS, [flow("g", "a"), flow("g", "b")])
    assert counts == {"tp": 2}


def test_a_flow_between_two_mentions_of_one_gateway_is_neither_right_nor_wrong():
    spans = [span("XOR Gateway", 0, "exclusiveGateway", "g"), span("XOR Gateway", 5, "exclusiveGateway", "h"),
             span("Activity", 9, "task", "a")]
    job = {"all_flows": [], "same_gateway": [[[0, 1], [5, 6]]]}
    assert score_all_flows(job, spans, ELEMENTS, [flow("g", "h"), flow("h", "a")]) == {"fp": 1}


def test_the_second_measure_holds_the_first_and_leaves_out_only_the_folding():
    assert set(SHAPES) <= ALL_SHAPES
    assert ("XOR Gateway", "Condition Specification") not in ALL_SHAPES
    assert ("XOR Gateway", "Activity") in ALL_SHAPES
