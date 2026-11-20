"""The strict Flow comparison (text2bpmn/pet_strict.py): the two scorers' rules
and the four rules that write the model as PET's Flow relations."""
import pytest

from text2bpmn import pet_strict as ps


def test_precision_and_recall_follow_their_stats_class():
    assert ps.prf(0, 0, 0)["f1"] == 1.0          # nothing to find and nothing found
    assert ps.prf(0, 3, 0)["f1"] == 0.0
    assert ps.prf(4, 0, 0)["p"] == 0.0
    s = ps.prf(4, 2, 1)
    assert (s["p"], s["r"]) == (0.5, 0.25)


def test_2024_matches_each_prediction_once_and_counts_duplicates_2023_counts_sets():
    gold = [("flow", "a", "b"), ("uses", "a", "c")]
    pred = [("flow", "a", "b"), ("flow", "a", "b"), ("flow", "b", "a")]
    assert ps.counts_2024(gold, pred) == (1, 3, 1)
    assert ps.counts_2023(gold, pred) == (1, 2, 1)


def test_the_folds_average_scores_and_pooling_sums_counts():
    per_document = {"d1": (2, 2, 2), "d2": (2, 2, 0)}
    assert ps.pooled(per_document)["f1"] == 0.5
    assert ps.fold_mean(per_document, [["d1"], ["d2"]])["f1"] == 0.5
    assert ps.fold_mean({"d1": (1, 1, 1), "d2": (9, 9, 0)}, [["d1"], ["d2"]])["f1"] == 0.5
    assert ps.pooled({"d1": (1, 1, 1), "d2": (9, 9, 0)})["f1"] == pytest.approx(0.1)


def test_an_answer_line_is_tag_head_tail_with_indices_into_the_mentions():
    keys = ["m0", "m1", "m2"]
    answer = "flow\t0\t1\nflow\t1\t2\twhy\nflow\t2\t9\nflow\tx\t1\nno tabs here\nflow\t0\t1\ta\tb"
    assert ps.parse_listing(answer, keys) == [("flow", "m0", "m1"), ("flow", "m1", "m2")]


def entity(group, start, end, eid, word=None, kind=None):
    kind = kind or {"XOR Gateway": "exclusiveGateway", "Condition Specification": "exclusiveGateway",
                    "AND Gateway": "parallelGateway"}.get(group, "task")
    return {"entity_group": group, "start": start, "end": end, "id": eid, "word": word or eid, "type": kind}


def seen(entities, flows, folded=None, plans=None, nodes=None):
    used = [{"id": e["id"], "label": e["entity_group"], "start": e["start"], "end": e["end"]} for e in entities]
    ids = {f[0] for f in flows} | {f[1] for f in flows}
    elements = [{"id": i} for i in ids]
    return {"result": {"entities_used": used,
                       "structured_data": {"elements": elements, "flows": [
                           {"source": s, "target": t, "name": n, "relation": r} for s, t, n, r in flows]}},
            "entities": entities, "decisions_mode": True, "folded": folded or {}, "plans": plans or {},
            "nodes": nodes or []}


IF, X = entity("XOR Gateway", 0, 2, "g", "If"), entity("Condition Specification", 3, 4, "c")
A, ELSE = entity("Activity", 6, 7, "a"), entity("XOR Gateway", 9, 18, "e", "Otherwise")
B, THEN = entity("Activity", 20, 21, "b"), entity("Activity", 28, 29, "n")


def spans(relations):
    return {(h[2], t[2]) for h, t in relations}


def test_a_condition_and_an_else_marker_are_written_as_pet_writes_them():
    # "If X, A. Otherwise B. Then C." built as g -Yes-> a, g -No-> b, both on to n
    model = seen([IF, A, ELSE, B, THEN],
                 [("StartEvent_1", "g", "", "SEQUENCE"), ("g", "a", "Yes", "TRUE_BRANCH"),
                  ("g", "b", "No", "FALSE_BRANCH"), ("a", "n", "", "SEQUENCE"), ("b", "n", "", "SEQUENCE"),
                  ("n", "EndEvent_1", "", "SEQUENCE")], folded={"g": [X]})
    assert spans(ps.render(model)) == {(2, 4), (4, 7), (18, 21), (7, 29), (21, 29)}
    # rule 1 alone: the decision itself heads both branches
    assert spans(ps.render(model, rules=False)) == {(2, 7), (2, 21), (7, 29), (21, 29)}


def test_a_case_opened_by_a_second_mention_leaves_from_that_mention_and_its_condition():
    if2, x2 = entity("XOR Gateway", 9, 11, "g2", "If"), entity("Condition Specification", 12, 13, "c2")
    nodes = [(IF, {"id": "g"}), (A, {"id": "a"}), (if2, {"id": "g2"}), (B, {"id": "b"}), (THEN, {"id": "n"})]
    plans = {0: {"cases": [("Yes", "TRUE_BRANCH", [1]), ("If not x", "TRUE_BRANCH", [3])], "no": [],
                 "goes_on": 4, "absorbed": {2}}}
    model = seen([IF, A, if2, B, THEN],
                 [("g", "a", "Yes", "TRUE_BRANCH"), ("g", "b", "If not x", "TRUE_BRANCH"),
                  ("a", "n", "", "SEQUENCE"), ("b", "n", "", "SEQUENCE")],
                 folded={"g": [X], "g2": [x2]}, plans=plans, nodes=nodes)
    assert spans(ps.render(model)) == {(2, 4), (4, 7), (11, 13), (13, 21), (7, 29), (21, 29)}


def test_a_decision_with_no_else_marker_heads_its_other_outcome_itself():
    model = seen([IF, A, THEN], [("g", "a", "Yes", "TRUE_BRANCH"), ("g", "n", "No", "FALSE_BRANCH"),
                                 ("a", "n", "", "SEQUENCE")], folded={"g": [X]})
    assert spans(ps.render(model)) == {(2, 4), (4, 7), (2, 29), (7, 29)}


def test_an_else_marker_stands_for_the_last_decision_before_it():
    entities = [IF, A, ELSE, B]
    assert {d: [e["id"] for e in es] for d, es in ps._else_markers(entities, True, True).items()} == {"g": ["e"]}
    alone = [A, ELSE, B]  # with no decision before it, the marker is a node of its own
    assert ps._else_markers(alone, True, True) == {}
