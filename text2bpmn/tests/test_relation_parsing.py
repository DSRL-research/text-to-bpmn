import pytest

from text2bpmn.relation_parsing import UNKNOWN, ParseFailureLog, parse_relation


def original_parse(raw, default):
    """The parsing both finder3.py and benchmark_relations.py used before C7,
    differing only in `default` (SEQUENCE and UNKNOWN respectively)."""
    raw = str(raw)
    if "Prediction:" in raw:
        raw = raw.split("Prediction:")[-1]
    lines = raw.replace("*", "").strip().split("\n")
    clean = lines[0].strip()
    labels = ["SEQUENCE", "TRUE_BRANCH", "FALSE_BRANCH", "PARALLEL", "CONDITION_DEF"]
    if clean in labels:
        return clean
    matched = next((v for v in labels if v in clean), default)
    if matched == default:
        for line in lines:
            hit = next((v for v in labels if v in line.replace("*", "").strip()), None)
            if hit:
                return hit
    return matched


RAW = ["TRUE_BRANCH", "**FALSE_BRANCH**", "Prediction: PARALLEL", "It is CONDITION_DEF.",
       "The relation is unclear\nFALSE_BRANCH", "none of these", "", "Prediction: **SEQUENCE**\nextra",
       "maybe", "sequence"]


@pytest.mark.parametrize("raw", RAW)
def test_same_labels_as_original_parser_only_the_default_changes(raw):
    new = parse_relation(raw)
    assert new == original_parse(raw, UNKNOWN)  # benchmark_relations.py, unchanged
    old = original_parse(raw, "SEQUENCE")  # finder3.py: its fallbacks now read UNKNOWN
    assert new == old or (new == UNKNOWN and old == "SEQUENCE")


def test_failure_log_counts_calls_and_keeps_raw_output():
    log = ParseFailureLog()
    assert log.parse("**TRUE_BRANCH**", node_A="a", node_B="b") == "TRUE_BRANCH"
    assert log.parse("I am not sure", node_A="c", node_B="d") == UNKNOWN
    assert log.error(TimeoutError("ollama down"), node_A="e", node_B="f") == UNKNOWN
    s = log.summary()
    assert (s["calls"], s["failures"]) == (3, 2) and s["rate"] == pytest.approx(2 / 3)
    assert s["records"][0] == {"node_A": "c", "node_B": "d", "raw_output": "I am not sure", "error": None}
    assert s["records"][1]["error"] == "ollama down"
