"""The release-run analyses: decisions one by one, lanes without recipients, and
tokens from vLLM's log (text2bpmn/checks/method_analysis.py, token_usage.py,
lane_accuracy.py)."""
from datetime import datetime

import pytest

from text2bpmn.checks.method_analysis import decision_outcomes, gold_decisions
from text2bpmn.checks.token_usage import in_window, log_intervals
from text2bpmn.lane_accuracy import expected_performers

G, C, A, E, B, N = (("xor gateway", 0, 2), ("condition specification", 3, 5), ("activity", 6, 8),
                    ("xor gateway", 9, 18), ("activity", 20, 22), ("activity", 28, 30))
DOC = {"text": "If xx, aa. Otherwise bb. Then cc." + " " * 10, "mentions": [G, C, A, E, B, N],
       "relations": [("flow", G, C), ("flow", C, A), ("flow", E, B), ("flow", A, N), ("flow", B, N),
                     ("same gateway", G, E)]}


def test_a_decision_is_its_mentions_linked_as_one_gateway_and_its_heads_are_where_its_flows_lead():
    [(members, conditions, heads)] = gold_decisions(DOC)
    assert members == {G, E} and conditions == {C} and heads == {A, B}


@pytest.mark.parametrize("built, outcome", [
    ({(G, C), (C, A), (E, B)}, "right: the same branch heads"),
    ({(G, C), (C, A)}, "not built: one way on or none"),
    ({(G, C), (C, A), (E, N)}, "a wrong branch head"),
    ({(G, C), (C, A), (E, B), (G, N)}, "an extra branch head"),
])
def test_each_gold_decision_gets_one_outcome(built, outcome):
    per_document, examples = decision_outcomes({"d": DOC}, {"d": built})
    assert dict(per_document["d"]) == {outcome: 1}
    assert outcome in examples


def span(group, start, word="w"):
    return {"entity_group": group, "start": start, "end": start + 1, "word": word}


def test_activities_with_an_actor_recipient_can_be_left_out_of_the_lane_score():
    act1, act2, clerk, client = span("Activity", 0), span("Activity", 5), span("Actor", 2, "clerk"), \
        span("Actor", 8, "client")
    doc = {"spans": [act1, act2, clerk, client],
           "relations": [("actor performer", act1, clerk), ("actor performer", act2, clerk),
                         ("actor recipient", act2, client)]}
    assert set(expected_performers(doc)) == {(0, 1), (5, 6)}
    assert set(expected_performers(doc, exclude_recipients=True)) == {(0, 1)}


LOG = """(APIServer pid=1) INFO 11-12 08:00:00 [loggers.py:320] Engine 000: Avg prompt throughput: 0.0 tokens/s, Avg generation throughput: 0.0 tokens/s, Running: 0 reqs
INFO:     127.0.0.1:1 - "POST /v1/chat/completions HTTP/1.1" 200 OK
(APIServer pid=1) INFO 11-12 08:00:10 [loggers.py:320] Engine 000: Avg prompt throughput: 100.0 tokens/s, Avg generation throughput: 20.0 tokens/s, Running: 1 reqs
(APIServer pid=1) INFO 11-12 08:00:30 [loggers.py:320] Engine 000: Avg prompt throughput: 10.0 tokens/s, Avg generation throughput: 5.0 tokens/s, Running: 0 reqs"""


def test_tokens_are_throughput_times_the_interval_since_the_line_before():
    intervals = log_intervals(LOG.splitlines())
    assert [(r[1], r[2], r[3]) for r in intervals] == [(0.0, 0.0, 0), (1000.0, 200.0, 1), (200.0, 100.0, 0)]
    prompt, generated, requests = in_window(intervals, datetime(2026, 11, 12, 8, 0, 5), datetime(2026, 11, 12, 8, 0, 25))
    assert (prompt, generated, requests) == (1200.0, 300.0, 1)
