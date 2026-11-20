"""Check, before a final run, that the vLLM server answers the way the run needs.

    python -m text2bpmn.remote.check_server --api-base URL --model ID [--api-key KEY]

Three things, each of which has gone wrong or could go wrong silently:

1. the server serves MODEL under that name, which is the name the run
   record keeps;
2. it decodes against the relation schema and honours the schema's length
   limit on `reasoning`. The final runs bound each reply that way; a server
   that dropped the limit would bring back the 120-second timeouts of
   2026-11-04 with no message, and one that dropped the schema would let a
   reply skip its answer;
3. thinking stays off when chat_template_kwargs asks for it;
4. the reply has no free whitespace between its JSON tokens. The JSON grammar
   allows any amount there, and Qwen3.5-27B used it: in 33 of 1297 PET calls it
   wrote carriage returns and spaces after the reasoning until the token limit
   cut the reply off before its answer (2026-11-09). Started with its
   disable-any-whitespace option, vLLM fixes the whitespace instead: xgrammar
   (vLLM 0.31) writes exactly one space after each colon and comma, as
   json.dumps does, and nothing else. Those single spaces are accepted; any
   other whitespace outside a string fails the check.

From the command line, a fifth, unless --no-decisions: it decodes against
the decision schema of text2bpmn/decisions.py, whose keys depend on the
question. The method's relation stage asks in that form since
revision-final-2 (the concurrency question of revision-final-3 has the same
form, with other labels).

The test request asks for long reasoning under a 40-character limit, so a
server that ignores the limit shows it at once, and for the JSON indented on
several lines, so a server whose grammar still allows free whitespace shows
that too. Exit status 0 when every check holds, 1 otherwise.
"""
import argparse
import json
import sys
import urllib.request

LIMIT = 40
QUESTION = ("Context: The clerk checks the form. Then the clerk files it.\n"
            "node_A: checks the form\nnode_B: files it\n"
            "Explain your reasoning in at least 150 words, then give the relation. "
            "Write the JSON pretty-printed, each key on its own line, indented by four spaces.")
DECISION_QUESTION = ("Text: [D]If the form is complete, the clerk [1]files it; otherwise the clerk "
                     "[2]returns it.\nDecision [D]: If the form is complete\nSteps:\n[1] Files it\n"
                     "[2] Returns it")


def free_whitespace(text):
    """How many whitespace characters a JSON text has outside its strings,
    beyond one space after each colon or comma (the separators a grammar
    without free whitespace still writes)."""
    count, inside, escaped, previous = 0, False, False, ""
    for char in text:
        if inside:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                inside = False
        elif char == '"':
            inside = True
        elif char.isspace() and not (char == " " and previous in (":", ",")):
            count += 1
        previous = "" if inside else char
    return count


def _request(url, key, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def check(api_base, model, key="EMPTY", timeout=120, decisions=False):
    """A list of (what, ok, detail), one per check."""
    from text2bpmn.finder3 import RELATION_LABELS, relation_schema

    base = api_base.rstrip("/")
    results = []
    served = [m.get("id") for m in _request(base + "/models", key, timeout=10).get("data", [])]
    results.append(("serves the model", model in served, f"serving {served}"))
    if model not in served:
        return results

    body = {"model": model, "temperature": 0, "max_tokens": 400,
            "messages": [{"role": "user", "content": QUESTION}],
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "relation", "schema": relation_schema(LIMIT)}}}
    reply = _request(base + "/chat/completions", key, body, timeout=timeout)
    content = reply["choices"][0]["message"].get("content") or ""
    try:
        answer = json.loads(content)
    except json.JSONDecodeError:
        answer = None
    shown = content[:120] + ("..." if len(content) > 120 else "")
    results.append(("decodes against the schema",
                    isinstance(answer, dict) and answer.get("relation") in RELATION_LABELS,
                    f"reply {shown!r}"))
    reasoning = answer.get("reasoning", "") if isinstance(answer, dict) else content
    results.append((f"honours the {LIMIT}-character limit on reasoning",
                    isinstance(answer, dict) and len(reasoning) <= LIMIT,
                    f"reasoning was {len(reasoning)} characters"))
    loose = free_whitespace(content)
    results.append(("no free whitespace between JSON tokens", loose == 0,
                    f"{loose} whitespace characters outside strings beyond one space after ':' and ','"
                    + ("" if loose == 0 else "; start vLLM with its disable-any-whitespace option")))
    results.append(("thinking is off", "<think>" not in content
                    and not reply["choices"][0]["message"].get("reasoning_content"),
                    "no <think> block" if "<think>" not in content else "the reply thinks"))
    if decisions:
        results.append(check_decisions(base, model, key, timeout))
    return results


def check_decisions(base, model, key, timeout):
    """Whether a decision question's reply decodes to one label per step."""
    from text2bpmn.decisions import INSTRUCTIONS, decision_schema, parse_answer

    body = {"model": model, "temperature": 0, "max_tokens": 400,
            "messages": [{"role": "system", "content": INSTRUCTIONS},
                         {"role": "user", "content": DECISION_QUESTION}],
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "decision", "schema": decision_schema(2, 200)}}}
    reply = _request(base + "/chat/completions", key, body, timeout=timeout)
    content = reply["choices"][0]["message"].get("content") or ""
    try:
        labels = parse_answer(content, 2)
    except ValueError:
        labels = None
    shown = content[:120] + ("..." if len(content) > 120 else "")
    return ("decodes against the decision schema", labels is not None,
            f"labels {labels}, reply {shown!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--decisions", action="store_true",
                    help="check the decision schema of text2bpmn/decisions.py (the default)")
    ap.add_argument("--no-decisions", action="store_true",
                    help="skip it, for a server that only answers the pairwise classifier")
    args = ap.parse_args(argv)
    results = check(args.api_base, args.model, args.api_key, decisions=not args.no_decisions)
    for what, ok, detail in results:
        print(f"   {'ok  ' if ok else 'FAIL'} {what}: {detail}")
    if not all(ok for _, ok, _ in results):
        print("   the server does not answer the way the final runs need; see above")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
