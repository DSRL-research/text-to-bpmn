"""text2bpmn/remote/check_server.py against a stand-in for vLLM."""
import json

from text2bpmn.remote import check_server

MODEL = "Qwen/Qwen3.5-27B-FP8"


def compact(value):
    """A reply as vLLM writes it with whitespace disabled."""
    return json.dumps(value, separators=(",", ":"))


def _server(monkeypatch, content, served=(MODEL,), reasoning_content=None):
    sent = []

    def request(url, key, body=None, timeout=120):
        sent.append((url, body))
        if url.endswith("/models"):
            return {"data": [{"id": m} for m in served]}
        message = {"role": "assistant", "content": content}
        if reasoning_content:
            message["reasoning_content"] = reasoning_content
        return {"choices": [{"message": message, "finish_reason": "stop"}]}

    monkeypatch.setattr(check_server, "_request", request)
    return sent


def _verdicts(monkeypatch, **server):
    _server(monkeypatch, **server)
    return {what: ok for what, ok, _ in check_server.check("http://localhost:11434/v1", MODEL)}


def test_a_server_that_honours_everything_passes(monkeypatch):
    sent = _server(monkeypatch, compact({"reasoning": "B follows A.", "relation": "SEQUENCE"}))
    results = check_server.check("http://localhost:11434/v1", MODEL)
    assert all(ok for _, ok, _ in results) and len(results) == 5
    body = sent[1][1]
    assert body["response_format"]["json_schema"]["schema"]["properties"]["reasoning"]["maxLength"] == \
        check_server.LIMIT
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert check_server.main(["--api-base", "http://localhost:11434/v1", "--model", MODEL, "--no-decisions"]) == 0
    # from the command line the decision schema is checked too, and a server that
    # answers it with the relation schema's reply fails it
    assert check_server.main(["--api-base", "http://localhost:11434/v1", "--model", MODEL]) == 1


def test_a_server_that_ignores_the_length_limit_fails(monkeypatch):
    verdicts = _verdicts(monkeypatch, content=compact({"reasoning": "x" * 900, "relation": "SEQUENCE"}))
    assert verdicts["decodes against the schema"]
    assert not verdicts[f"honours the {check_server.LIMIT}-character limit on reasoning"]


def test_a_reply_without_the_answer_field_fails(monkeypatch):
    verdicts = _verdicts(monkeypatch, content=compact({"reasoning": "never answers"}))
    assert not verdicts["decodes against the schema"]


def test_a_thinking_reply_fails(monkeypatch):
    verdicts = _verdicts(monkeypatch, content="<think>long</think>{}")
    assert not verdicts["thinking is off"]


def test_a_model_served_under_another_name_stops_the_check(monkeypatch):
    _server(monkeypatch, content="", served=("qwen3big",))
    results = check_server.check("http://localhost:11434/v1", MODEL)
    assert [ok for _, ok, _ in results] == [False]
    assert check_server.main(["--api-base", "http://localhost:11434/v1", "--model", MODEL]) == 1


def test_a_reply_with_whitespace_between_its_tokens_fails(monkeypatch):
    """With the grammar's free whitespace, Qwen3.5-27B looped on carriage
    returns after its reasoning until the token limit cut off the answer."""
    verdicts = _verdicts(monkeypatch, content='{\n  "reasoning": "B follows A."\n  ,\n  "relation": "SEQUENCE"\n}')
    assert verdicts["decodes against the schema"]
    assert not verdicts["no free whitespace between JSON tokens"]


def test_xgrammars_fixed_separators_pass(monkeypatch):
    """vLLM 0.31 with xgrammar and disable_any_whitespace, 2026-11-09: one space
    after each colon and comma, nothing else."""
    content = '{"reasoning": "The relationship between the two nodes, ", "relation": "SEQUENCE"}'
    assert content == json.dumps(json.loads(content))
    verdicts = _verdicts(monkeypatch, content=content)
    assert all(verdicts.values())


def test_the_loop_of_2026_11_09_fails(monkeypatch):
    verdicts = _verdicts(monkeypatch, content='{"reasoning": "B follows A.",' + "\r  " * 300)
    assert not verdicts["no free whitespace between JSON tokens"]


def test_only_one_space_after_a_separator_is_allowed():
    from text2bpmn.remote.check_server import free_whitespace
    assert free_whitespace('{"reasoning":"a b \\" c","relation":"SEQUENCE"}') == 0
    assert free_whitespace('{"reasoning": "a, b: c", "relation": "SEQUENCE"}') == 0
    assert free_whitespace('{"reasoning":  "a"}') == 1
    assert free_whitespace('{ "reasoning": "a" }') == 2
    assert free_whitespace('{"reasoning": "a",\n"relation": "SEQUENCE"}') == 1
    assert free_whitespace('{\n    "reasoning": "a",\n    "relation": "SEQUENCE"\n}') == 11


def test_the_decision_schema_is_checked_only_when_asked(monkeypatch):
    def request(url, key, body=None, timeout=120):
        if url.endswith("/models"):
            return {"data": [{"id": MODEL}]}
        if body["response_format"]["json_schema"]["name"] == "decision":
            content = '{"reasoning": "Files when complete.", "step_1": "yes", "step_2": "no"}'
        else:
            content = '{"reasoning": "B follows A.", "relation": "SEQUENCE"}'
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}

    monkeypatch.setattr(check_server, "_request", request)
    assert len(check_server.check("http://localhost:11434/v1", MODEL)) == 5
    results = check_server.check("http://localhost:11434/v1", MODEL, decisions=True)
    assert results[-1][:2] == ("decodes against the decision schema", True)
    assert "['yes', 'no']" in results[-1][2]


def test_a_decision_reply_missing_a_step_fails(monkeypatch):
    _server(monkeypatch, '{"reasoning": "r", "step_1": "yes"}')
    results = check_server.check("http://localhost:11434/v1", MODEL, decisions=True)
    assert results[-1][:2] == ("decodes against the decision schema", False)
