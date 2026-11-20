"""Relation idea 1: one question per decision, on the text-order chain."""
from types import SimpleNamespace

import pytest

from text2bpmn import decisions
from text2bpmn.relation_parsing import ParseFailureLog
from text2bpmn.run_config import RunConfig
from text2bpmn.structure import validate
from text2bpmn.tests.test_finder3 import entities

TEXT = ("The clerk checks the invoice. If the amount is high, the manager approves it. "
        "Otherwise, the clerk approves it. Then the clerk pays the invoice.")
SPANS = [("Actor", "The clerk"), ("Activity", "checks"), ("Activity Data", "the invoice"),
         ("XOR Gateway", "If"), ("Condition Specification", "the amount is high"),
         ("Actor", "the manager"), ("Activity", "approves"), ("XOR Gateway", "Otherwise"),
         ("Actor", "the clerk"), ("Activity", "approves"), ("Activity", "pays"),
         ("Activity Data", "the invoice")]


@pytest.fixture
def extractor():
    from text2bpmn.tests.test_finder3 import BPMNHybridExtractor
    import spacy

    x = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    x.dspy_predictor = None
    x.relation_log = ParseFailureLog()
    x.config = RunConfig(relation_mode="decisions")
    x.nlp_validator = spacy.load("en_core_web_sm")
    return x


def structure(extractor, monkeypatch, answer):
    """The process data, with the decision question answered by `answer`."""
    asked = []

    def ask(context, decision, steps, lanes, kinds=None):
        asked.append((decision["clean_name"], [s["clean_name"] for s in steps], lanes))
        return answer(len(steps)) if callable(answer) else answer

    monkeypatch.setattr(extractor, "_ask_decision", ask)
    return extractor._structure_process_data(entities(*SPANS, text=TEXT), TEXT), asked


def edges(data):
    name = {e["id"]: e["name"] + (f"/{e['lane']}" if e["type"] == "task" else "") for e in data["elements"]}
    return {(name[f["source"]], name[f["target"]], f.get("name", "")) for f in data["flows"]}


def test_the_decision_is_asked_about_the_steps_after_it_without_the_else_marker(extractor, monkeypatch):
    _, asked = structure(extractor, monkeypatch, None)
    assert asked == [("If the amount is high", ["Approves", "Approves", "Pays the invoice"],
                      ["The manager", "The clerk", "The clerk"])]


def test_the_branches_split_at_the_decision_and_join_at_the_first_after_step(extractor, monkeypatch):
    data, _ = structure(extractor, monkeypatch, ["yes", "no", "after"])
    assert edges(data) == {
        ("Start", "Checks the invoice/The clerk", ""),
        ("Checks the invoice/The clerk", "If the amount is high", ""),
        ("If the amount is high", "Approves/The manager", "Yes"),
        ("If the amount is high", "Approves/The clerk", "No"),
        ("Approves/The manager", "Pays the invoice/The clerk", ""),
        ("Approves/The clerk", "Pays the invoice/The clerk", ""),
        ("Pays the invoice/The clerk", "End", "")}
    assert not any(e["name"] == "Otherwise" for e in data["elements"])
    validate(data)  # the Validation Layer takes it as it is


CHAIN = {("Start", "Checks the invoice/The clerk", ""),
         ("Checks the invoice/The clerk", "If the amount is high", ""),
         ("If the amount is high", "Approves/The manager", ""),
         ("Approves/The manager", "Approves/The clerk", ""),
         ("Approves/The clerk", "Pays the invoice/The clerk", ""),
         ("Pays the invoice/The clerk", "End", "")}


@pytest.mark.parametrize("answer", [None, ["after", "after", "after"]],
                         ids=["the call failed", "not a decision"])
def test_without_branches_the_chain_stays(extractor, monkeypatch, answer):
    data, _ = structure(extractor, monkeypatch, answer)
    assert edges(data) == CHAIN


def test_an_empty_branch_goes_from_the_decision_to_the_step_after_it(extractor, monkeypatch):
    data, _ = structure(extractor, monkeypatch, ["yes", "after", "after"])
    assert {("If the amount is high", "Approves/The manager", "Yes"),
            ("If the amount is high", "Approves/The clerk", "No"),
            ("Approves/The manager", "Approves/The clerk", "")} <= edges(data)


def test_branches_with_no_after_step_meet_at_what_follows_them(extractor, monkeypatch):
    data, _ = structure(extractor, monkeypatch, ["yes", "no", "no"])
    assert {("Approves/The manager", "End", ""), ("Pays the invoice/The clerk", "End", ""),
            ("Approves/The clerk", "Pays the invoice/The clerk", "")} <= edges(data)


def node(kind, name, start=None):
    return ({"id": name, "clean_name": name, "word": name, "type": kind, "start": start},
            {"id": name, "name": name, "type": kind, "lane": "Main Process"})


def test_a_question_lists_the_steps_up_to_the_next_gateway_or_the_limit():
    seen = []
    ask = lambda d, steps, lanes: seen.append([s["id"] for s in steps])  # noqa: E731
    decisions.plan([node("exclusiveGateway", "g1"), node("task", "a"), node("task", "b"),
                    node("exclusiveGateway", "g2"), node("task", "c")], ask)
    assert seen == [["a", "b"], ["c"]]
    seen.clear()
    decisions.plan([node("exclusiveGateway", "g")] + [node("task", f"t{i}") for i in range(12)], ask)
    assert len(seen[0]) == decisions.MAX_STEPS


def test_the_first_after_ends_the_decision():
    assert decisions.branches(["yes", "no", "after", "yes"]) == ([0], [1], 2)
    assert decisions.branches(["no", "no"]) == ([], [0, 1], None)


def test_the_marks_go_before_each_span():
    text = "If it rains, take a coat. Leave."
    marked = decisions.marked_text(text, {"start": 0}, [{"start": 13}, {"start": 26}])
    assert marked == "[D]If it rains, [1]take a coat. [2]Leave."


def test_the_schema_has_the_reasoning_first_and_one_closed_key_per_step():
    schema = decisions.decision_schema(2, 2000)
    assert list(schema["properties"]) == ["reasoning", "step_1", "step_2"]
    assert schema["required"] == ["reasoning", "step_1", "step_2"]
    assert schema["properties"]["step_2"]["enum"] == ["yes", "no", "after"]
    assert schema["properties"]["reasoning"]["maxLength"] == 2000


def test_a_reply_parses_only_when_every_step_has_a_label():
    assert decisions.parse_answer('{"reasoning": "r", "step_1": "Yes", "step_2": "after"}', 2) == ["yes", "after"]
    for bad in ('{"reasoning": "r", "step_1": "yes"}', '{"step_1": "maybe", "step_2": "no"}', "no json"):
        with pytest.raises(ValueError):
            decisions.parse_answer(bad, 2)


def test_ask_llm_sends_the_decision_schema_when_answers_are_constrained():
    calls = []

    def lm(messages, **options):
        calls.append((messages, options))
        return ['{"reasoning": "r", "step_1": "yes"}']

    config = SimpleNamespace(constrained_output=True, reasoning_max_chars=100)
    labels = decisions.ask_llm(lm, "If x, do it.", {"start": 0, "clean_name": "If x"},
                               [{"start": 6, "clean_name": "Do it"}], lambda e: e["clean_name"], ["Main Process"],
                               config)
    assert labels == ["yes"]
    messages, options = calls[0]
    assert messages[0]["content"] == decisions.INSTRUCTIONS
    assert "[D]If x, [1]do it." in messages[1]["content"] and "[1] Do it" in messages[1]["content"]
    schema = options["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["reasoning", "step_1"]


def test_without_a_predictor_the_question_is_a_logged_failure(extractor):
    from text2bpmn.finder3 import BPMNHybridExtractor

    found = entities(*SPANS, text=TEXT)
    for e in found:
        e["clean_name"] = e["word"]
    assert BPMNHybridExtractor._ask_decision(extractor, TEXT, found[3], found[6:7], ["x"]) is None
    assert extractor.relation_log.summary()["failures"] == 1


# --- idea 1b: later mentions of the same decision ---------------------------

STOCK = ("If the item is in stock, the clerk ships it. If it is not in stock, the clerk orders it. "
         "The clerk then sends the invoice.")
STOCK_SPANS = [("XOR Gateway", "If"), ("Condition Specification", "the item is in stock"),
               ("Actor", "the clerk"), ("Activity", "ships"), ("XOR Gateway", "If"),
               ("Condition Specification", "it is not in stock"), ("Actor", "the clerk"),
               ("Activity", "orders"), ("Actor", "The clerk"), ("Activity", "sends"),
               ("Activity Data", "the invoice")]


def stock(extractor, monkeypatch, answers):
    """The stock text in mode decisions2, each question answered in turn."""
    extractor.config = RunConfig(relation_mode="decisions2")
    asked, queue = [], list(answers)

    def ask(context, decision, steps, lanes, kinds=None):
        asked.append((decision["clean_name"], [s["clean_name"] for s in steps], kinds))
        return queue.pop(0)

    monkeypatch.setattr(extractor, "_ask_decision", ask)
    return extractor._structure_process_data(entities(*STOCK_SPANS, text=STOCK), STOCK), asked


def test_1b_lists_later_decisions_and_a_same_mention_opens_another_branch(extractor, monkeypatch):
    data, asked = stock(extractor, monkeypatch, [["yes", "same", "yes", "after"]])
    assert asked == [("If the item is in stock", ["Ships", "If it is not in stock", "Orders", "Sends the invoice"],
                      ["step", "decision", "step", "step"])]  # one question: the second mention is absorbed
    assert edges(data) == {
        ("Start", "If the item is in stock", ""),
        ("If the item is in stock", "Ships/The clerk", "Yes"),
        ("If the item is in stock", "Orders/The clerk", "If it is not in stock"),
        ("Ships/The clerk", "Sends the invoice/The clerk", ""),
        ("Orders/The clerk", "Sends the invoice/The clerk", ""),
        ("Sends the invoice/The clerk", "End", "")}
    assert not any(e["name"] == "If it is not in stock" for e in data["elements"])
    validate(data)


def test_1b_a_decision_of_its_own_ends_the_question_and_gets_one_of_its_own(extractor, monkeypatch):
    data, asked = stock(extractor, monkeypatch, [["yes", "after", "after", "after"], ["yes", "after"]])
    assert [a[0] for a in asked] == ["If the item is in stock", "If it is not in stock"]
    assert {("If the item is in stock", "Ships/The clerk", "Yes"),
            ("If the item is in stock", "If it is not in stock", "No"),
            ("Ships/The clerk", "If it is not in stock", "")} <= edges(data)


def test_1b_with_several_cases_and_no_else_there_is_no_default_branch(extractor, monkeypatch):
    data, _ = stock(extractor, monkeypatch, [["yes", "same", "yes", "after"]])
    out_of_decision = [f for f in data["flows"] if f["source"] == next(
        e["id"] for e in data["elements"] if e["name"] == "If the item is in stock")]
    assert len(out_of_decision) == 2


def test_1b_schema_and_question_give_a_decision_mention_its_own_labels():
    schema = decisions.decision_schema(2, None, ["step", "decision"])
    assert schema["properties"]["step_1"]["enum"] == ["yes", "no", "after"]
    assert schema["properties"]["step_2"]["enum"] == ["same", "after"]
    name = lambda e: e["clean_name"]  # noqa: E731
    text = decisions.question("If a, do b. If c, d.", {"start": 0, "clean_name": "If a"},
                              [{"start": 6, "clean_name": "Do b"}, {"start": 12, "clean_name": "If c"}],
                              name, ["Main Process", "Main Process"], ["step", "decision"])
    assert text.endswith("Marked:\n[1] Do b\n[2] decision: If c")
    with pytest.raises(ValueError):
        decisions.parse_answer('{"step_1": "yes", "step_2": "yes"}', 2, ["step", "decision"])


def test_idea_1_asks_exactly_as_it_did_on_the_server():
    """The question idea 1 put to the model on 2026-11-11 is unchanged by 1b."""
    name = lambda e: e["clean_name"]  # noqa: E731
    text = decisions.question("If a, do b.", {"start": 0, "clean_name": "If a"},
                              [{"start": 6, "clean_name": "Do b"}], name, ["The clerk"])
    assert text == "Text: [D]If a, [1]do b.\nDecision [D]: If a\nSteps:\n[1] Do b (The clerk)"
    assert decisions.decision_schema(1, 5) == {
        "type": "object", "properties": {"reasoning": {"type": "string", "maxLength": 5},
                                         "step_1": {"type": "string", "enum": ["yes", "no", "after"]}},
        "required": ["reasoning", "step_1"]}
