"""Relation idea 3: one question per concurrency word, on top of idea 1c."""
from types import SimpleNamespace

import pytest

from text2bpmn import decisions
from text2bpmn.pet_flow_eval import score_concurrency
from text2bpmn.relation_parsing import ParseFailureLog
from text2bpmn.run_config import RunConfig
from text2bpmn.structure import validate
from text2bpmn.tests.test_decisions import edges, node
from text2bpmn.tests.test_finder3 import entities

ORDER = ("The clerk registers the order. In the meantime, the warehouse picks the goods and packs them. "
         "Then the courier collects the parcel.")
ORDER_SPANS = [("Actor", "The clerk"), ("Activity", "registers"), ("Activity Data", "the order"),
               ("AND Gateway", "In the meantime"), ("Actor", "the warehouse"), ("Activity", "picks"),
               ("Activity Data", "the goods"), ("Activity", "packs"), ("Actor", "the courier"),
               ("Activity", "collects"), ("Activity Data", "the parcel")]


@pytest.fixture
def extractor():
    from text2bpmn.tests.test_finder3 import BPMNHybridExtractor
    import spacy

    x = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    x.dspy_predictor = None
    x.relation_log = ParseFailureLog()
    x.config = RunConfig(relation_mode="decisions4")
    x.nlp_validator = spacy.load("en_core_web_sm")
    return x


def structure(extractor, monkeypatch, text, spans, parallel, decision=None, mode="decisions4"):
    """The process data in `mode`, each concurrency question answered in turn
    from `parallel` and each decision question from `decision`."""
    extractor.config = RunConfig(relation_mode=mode)
    asked, answers, decided = [], list(parallel), list(decision or [])

    def ask_parallel(context, cue, steps, lanes):
        asked.append((cue["clean_name"], [s["clean_name"] for s in steps], lanes))
        return answers.pop(0) if answers else None

    def ask_decision(context, d, steps, lanes, kinds=None):
        return decided.pop(0) if decided else None

    monkeypatch.setattr(extractor, "_ask_parallel", ask_parallel)
    monkeypatch.setattr(extractor, "_ask_decision", ask_decision)
    return extractor._structure_process_data(entities(*spans, text=text), text), asked


def test_the_word_is_asked_about_the_steps_before_and_after_it(extractor, monkeypatch):
    _, asked = structure(extractor, monkeypatch, ORDER, ORDER_SPANS, [None])
    assert asked == [("In the meantime", ["Registers the order", "Picks the goods", "Packs", "Collects the parcel"],
                      ["The clerk", "The warehouse", "The warehouse", "The courier"])]


def test_two_lines_become_a_parallel_block_that_the_validation_layer_joins(extractor, monkeypatch):
    data, _ = structure(extractor, monkeypatch, ORDER, ORDER_SPANS, [["a", "b", "b", "after"]])
    assert edges(data) == {
        ("Start", "In the meantime", ""),
        ("In the meantime", "Registers the order/The clerk", ""),
        ("In the meantime", "Picks the goods/The warehouse", ""),
        ("Picks the goods/The warehouse", "Packs/The warehouse", ""),
        ("Registers the order/The clerk", "Collects the parcel/The courier", ""),
        ("Packs/The warehouse", "Collects the parcel/The courier", ""),
        ("Collects the parcel/The courier", "End", ""),
    }
    assert next(e for e in data["elements"] if e["name"] == "In the meantime")["type"] == "parallelGateway"
    process = validate(data)
    assert sorted(n.kind for n in process.nodes.values() if n.kind.endswith("Gateway")) == \
        ["parallelGateway", "parallelGateway"]  # the word's split and the join the layer adds


def test_a_step_before_the_lines_stays_in_the_chain(extractor, monkeypatch):
    data, _ = structure(extractor, monkeypatch, ORDER, ORDER_SPANS, [["before", "a", "b", "after"]])
    assert {("Start", "Registers the order/The clerk", ""),
            ("Registers the order/The clerk", "In the meantime", ""),
            ("In the meantime", "Picks the goods/The warehouse", ""),
            ("In the meantime", "Packs/The warehouse", ""),
            ("Picks the goods/The warehouse", "Collects the parcel/The courier", ""),
            ("Packs/The warehouse", "Collects the parcel/The courier", "")} <= edges(data)
    validate(data)


@pytest.mark.parametrize("answer", [None, ["before"] * 4, ["a", "a", "after", "after"],
                                    ["a", "before", "b", "after"], ["after", "a", "b", "after"]])
def test_without_two_lines_the_word_is_left_out_as_in_1c(extractor, monkeypatch, answer):
    data, _ = structure(extractor, monkeypatch, ORDER, ORDER_SPANS, [answer])
    plain, _ = structure(extractor, monkeypatch, ORDER, ORDER_SPANS, [], mode="decisions3")
    assert edges(data) == edges(plain)
    assert "In the meantime" not in {e["name"] for e in data["elements"]}


FILES = ("If files are missing, the clerk searches them, otherwise the clerk tracks them. The clerk "
         "hands them over, and meantime the judge distributes the list. Afterwards the judge holds the hearing.")
FILES_SPANS = [("XOR Gateway", "If"), ("Condition Specification", "files are missing"), ("Actor", "the clerk"),
               ("Activity", "searches"), ("XOR Gateway", "otherwise"), ("Actor", "the clerk"),
               ("Activity", "tracks"), ("Actor", "The clerk"), ("Activity", "hands"),
               ("AND Gateway", "meantime"), ("Actor", "the judge"), ("Activity", "distributes"),
               ("Activity Data", "the list"), ("Actor", "the judge"), ("Activity", "holds"),
               ("Activity Data", "the hearing")]


def test_a_block_after_a_decision_starts_where_its_branches_meet(extractor, monkeypatch):
    # PET doc-3.2's shape: both outcomes of the decision lead into the split
    data, asked = structure(extractor, monkeypatch, FILES, FILES_SPANS, [["a", "b", "after"]],
                            decision=[["yes", "no", "after", "after", "after"]])
    assert asked == [("Meantime", ["Hands", "Distributes the list", "Holds the hearing"],
                      ["The clerk", "The judge", "The judge"])]  # not the steps in the decision's branches
    assert {("Searches/The clerk", "Meantime", ""), ("Tracks/The clerk", "Meantime", ""),
            ("Meantime", "Hands/The clerk", ""), ("Meantime", "Distributes the list/The judge", ""),
            ("Hands/The clerk", "Holds the hearing/The judge", ""),
            ("Distributes the list/The judge", "Holds the hearing/The judge", "")} <= edges(data)
    process = validate(data)
    kinds = sorted(n.kind for n in process.nodes.values() if n.kind.endswith("Gateway"))
    assert kinds == ["exclusiveGateway", "exclusiveGateway", "parallelGateway", "parallelGateway"]


def test_the_window_stops_at_decisions_their_branches_and_the_limits():
    seen = []

    def ask(cue, steps, lanes):
        seen.append([s["id"] for s in steps])
        return None

    nodes = [node("task", "t0"), node("exclusiveGateway", "g"), node("task", "t2"), node("task", "t3"),
             node("task", "t4"), node("exclusiveGateway", "h"), node("task", "t6")]
    cue = node("parallelGateway", "p")
    decisions.parallel_plan(nodes, [(*cue, 4)], {1: {"goes_on": 3}}, ask)
    assert seen == [["t3", "t4"]]  # t2 is in g's branch; h is a decision
    seen.clear()
    many = [node("task", f"t{i}") for i in range(12)]
    decisions.parallel_plan(many, [(*cue, 5)], {}, ask)
    assert seen == [[f"t{i}" for i in range(5 - decisions.MAX_BEFORE, 5 + decisions.MAX_AFTER)]]


def test_a_later_word_cannot_reuse_the_steps_of_an_earlier_block():
    seen = []
    nodes = [node("task", f"t{i}") for i in range(6)]
    answers = [["a", "b", "after", "after", "after", "after"], None]

    def ask(cue, steps, lanes):
        seen.append([s["id"] for s in steps])
        return answers.pop(0)

    blocks = decisions.parallel_plan(nodes, [(*node("parallelGateway", "p"), 1),
                                             (*node("parallelGateway", "q"), 3)], {}, ask)
    assert blocks == {0: {"gateway": node("parallelGateway", "p")[1], "lines": [[0], [1]], "goes_on": 2}}
    assert seen[1] == ["t2", "t3", "t4", "t5"]


def test_the_lines_are_read_from_the_labels():
    assert decisions.parallel_lines(["before", "a", "b", "a", "after", "b"]) == (1, [[1, 3], [2]], 4)
    assert decisions.parallel_lines(["a", "b", "c"]) == (0, [[0], [1], [2]], 3)
    assert decisions.parallel_lines(["a", "c", "after"]) == (0, [[0], [1]], 2)
    for one_line_or_broken in (["a", "a"], ["before", "before"], ["a", "before", "b"], ["after", "a", "b"]):
        assert decisions.parallel_lines(one_line_or_broken) is None


def test_the_schema_and_the_reply():
    schema = decisions.parallel_schema(2, 2000)
    assert list(schema["properties"]) == ["reasoning", "step_1", "step_2"]
    assert schema["properties"]["step_1"]["enum"] == ["before", "a", "b", "c", "after"]
    assert schema["properties"]["reasoning"]["maxLength"] == 2000
    assert decisions.parse_parallel('{"reasoning": "r", "step_1": "A", "step_2": "after"}', 2) == ["a", "after"]
    for bad in ('{"reasoning": "r", "step_1": "a"}', '{"step_1": "yes", "step_2": "b"}', "no json"):
        with pytest.raises(ValueError):
            decisions.parse_parallel(bad, 2)


def test_ask_parallel_llm_marks_the_word_and_sends_its_schema():
    calls = []

    def lm(messages, **options):
        calls.append((messages, options))
        return ['{"reasoning": "r", "step_1": "a", "step_2": "b"}']

    text = "A is done. Meanwhile B is done."
    config = SimpleNamespace(constrained_output=True, reasoning_max_chars=100)
    labels = decisions.ask_parallel_llm(lm, text, {"start": 11, "clean_name": "Meanwhile"},
                                        [{"start": 0, "clean_name": "A"}, {"start": 21, "clean_name": "B"}],
                                        lambda e: e["clean_name"], ["X", "Main Process"], config)
    assert labels == ["a", "b"]
    messages, options = calls[0]
    assert messages[0]["content"] == decisions.INSTRUCTIONS_PARALLEL
    assert "Text: [1]A is done. [P]Meanwhile [2]B is done." in messages[1]["content"]
    assert "Words [P]: Meanwhile" in messages[1]["content"]
    assert "[1] A (X)" in messages[1]["content"] and "[2] B\n" not in messages[1]["content"]
    assert options["response_format"]["json_schema"]["name"] == "parallel"


def test_without_a_predictor_the_question_is_a_logged_failure(extractor):
    from text2bpmn.finder3 import BPMNHybridExtractor

    found = entities(*ORDER_SPANS, text=ORDER)
    for e in found:
        e["clean_name"] = e["word"]
    assert BPMNHybridExtractor._ask_parallel(extractor, ORDER, found[3], found[5:8], ["x"] * 3) is None
    assert extractor.relation_log.summary()["failures"] == 1


# --- the third PET measure ----------------------------------------------------

def span(label, start, element=None):
    return {"entity_group": label, "start": start, "end": start + 1, "id": element}


ELEMENTS = {i: {"id": i, "type": t} for i, t in
            (("p", "parallelGateway"), ("a", "task"), ("b", "task"), ("c", "task"), ("x", "exclusiveGateway"))}
SPANS = [span("Activity", 0, "a"), span("AND Gateway", 3), span("Activity", 6, "b"), span("Activity", 9, "c")]
JOB = {"all_flows": [{"source": [3, 4], "target": [0, 1], "source_label": "AND Gateway"},
                     {"source": [3, 4], "target": [6, 7], "source_label": "AND Gateway"},
                     {"source": [6, 7], "target": [9, 10], "source_label": "Activity"}]}


def flow(source, target, name=""):
    return {"source": source, "target": target, "name": name}


def test_a_pair_counts_when_both_lines_leave_one_parallel_split():
    assert score_concurrency(JOB, SPANS, ELEMENTS, [flow("p", "a"), flow("p", "b"), flow("b", "c")]) == \
        {"unmapped": 0, "tp": 1, "fn": 0, "fp": 0}
    # in text order the pair is missed; side by side with the wrong step it is wrong too
    assert score_concurrency(JOB, SPANS, ELEMENTS, [flow("a", "b"), flow("b", "c")]) == \
        {"unmapped": 0, "tp": 0, "fn": 1, "fp": 0}
    assert score_concurrency(JOB, SPANS, ELEMENTS, [flow("p", "a"), flow("p", "c")]) == \
        {"unmapped": 0, "tp": 0, "fn": 1, "fp": 1}


def test_a_task_with_unlabelled_flows_is_a_split_and_a_decision_is_not():
    assert score_concurrency(JOB, SPANS, ELEMENTS, [flow("c", "a"), flow("c", "b")])["tp"] == 1
    assert score_concurrency(JOB, SPANS, ELEMENTS, [flow("x", "a", "Yes"), flow("x", "b", "No")])["tp"] == 0
    assert score_concurrency(JOB, SPANS, ELEMENTS, [flow("c", "a", "Yes"), flow("c", "b")])["tp"] == 0
