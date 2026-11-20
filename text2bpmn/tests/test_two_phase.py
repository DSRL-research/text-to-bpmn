import pytest

from text2bpmn.two_phase import (TRIGGER, build_prompt, classify, constraint,
                                 is_hard, overlap)


def test_a_marker_word_as_a_node_is_hard():
    assert is_hard("Checks", "Or") == "a gateway marker as a node"
    assert is_hard("Takes her computer", "Whereas") == "a gateway marker as a node"


def test_a_condition_specification_as_a_node_is_hard():
    reason = is_hard("Assigns the MPON", "If the MPON informs the GO about the outcome")
    assert reason == "a condition specification as a node"


def test_mirrored_activities_are_hard():
    reason = is_hard("Confirmes the changes of the INQ", "Rejectes the changes of the INQ")
    assert reason == "two near-identical activities"


def test_an_ordinary_pair_is_not_worth_the_second_call():
    assert is_hard("Sends the form", "Archives the record") is None
    # the first smoke test sent this one down the expensive path, because "the"
    # and "form" made it look 0.67 identical
    assert is_hard("Receives the form", "Files the form") is None


def test_overlap_is_measured_against_the_shorter_node():
    assert overlap("the changes of the INQ", "rejects the changes of the INQ") == 1.0
    assert overlap("", "anything") == 0.0


def test_vllm_and_ollama_get_different_constraints():
    assert "guided_choice" in constraint("openai")["extra_body"]
    schema = constraint("ollama")["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["relation"]["enum"][0] == "SEQUENCE"


class FakeCompletion:
    """Records both calls and replies to each in turn."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        body = self.replies[len(self.calls) - 1]
        message = type("M", (), {"content": body})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


def test_the_first_call_is_free_and_the_second_is_constrained():
    fake = FakeCompletion("I think this is a branch, but it could be a sequence",
                          '{"relation": "FALSE_BRANCH"}')
    label, record = classify("Otherwise, reject.", "Otherwise", "reject",
                             model="ollama/x", api_base="http://x", completion=fake)
    assert label == "FALSE_BRANCH"

    free, constrained = fake.calls
    assert "stop" not in free                     # it must be allowed to finish a thought
    assert "response_format" not in free          # nothing constrains the thinking
    assert "guided_choice" not in free.get("extra_body", {})
    assert "response_format" in constrained       # the answer is closed
    assert record["reasoning_characters"] > 0


def test_the_second_call_carries_the_reasoning_and_the_trigger():
    fake = FakeCompletion("because the condition fails", '{"relation": "FALSE_BRANCH"}')
    classify("c", "a", "b", model="ollama/x", api_base="http://x", completion=fake)
    messages = fake.calls[1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"] == "because the condition fails"
    assert messages[-1]["content"].startswith(TRIGGER)


def test_an_answer_naming_no_label_is_unknown_not_a_guess():
    fake = FakeCompletion("thinking", "I am not sure")
    label, _ = classify("c", "a", "b", model="ollama/x", api_base="http://x",
                        completion=fake)
    assert label == "UNKNOWN"


def test_the_first_prompt_asks_for_reasoning_and_withholds_the_label():
    prompt = build_prompt("Decide the relation.", "ctx", "A", "B")
    assert "node_A: A" in prompt
    assert "Do not state the label yet" in prompt
    # naming the trigger here is what made the model emit it first and reason
    # for zero characters
    assert TRIGGER not in prompt


def test_thinking_is_disabled_on_both_calls_when_asked():
    """A hybrid model must not reason in either phase.

    Qwen3 opens a <think> block by default. Phase two allows 16 tokens, so the
    whole budget is spent inside that block, the content comes back naming no
    label, and every hard pair resolves to UNKNOWN -- which is what a whole
    45-document run did before this was plumbed through.
    """
    fake = FakeCompletion("reasoning", "FALSE_BRANCH")
    label, _ = classify("c", "a", "b", model="hosted_vllm/x", api_base="http://x",
                        backend="openai", disable_thinking=True, completion=fake)
    assert label == "FALSE_BRANCH"
    for call in fake.calls:
        assert call["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    # and the answer is still closed to the five labels
    assert "guided_choice" in fake.calls[1]["extra_body"]


def test_thinking_is_left_alone_by_default():
    fake = FakeCompletion("reasoning", "SEQUENCE")
    classify("c", "a", "b", model="hosted_vllm/x", api_base="http://x",
             backend="openai", completion=fake)
    for call in fake.calls:
        assert "chat_template_kwargs" not in call.get("extra_body", {})


def test_ollama_has_nothing_to_turn_off():
    fake = FakeCompletion("reasoning", '{"relation": "SEQUENCE"}')
    classify("c", "a", "b", model="ollama/x", api_base="http://x",
             backend="ollama", disable_thinking=True, completion=fake)
    assert "extra_body" not in fake.calls[0]
