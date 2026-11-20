"""Symbolic guardrails applied after the LLM's relation prediction.

FALSE_BRANCH guardrail: a SEQUENCE prediction becomes FALSE_BRANCH when the
pair carries an explicit else-marker. In the annotation scheme the marker is
the source entity, e.g. {"entity_1": "Otherwise", "entity_2": "replies via
email", "label": "FALSE_BRANCH"}. finder3.py and benchmark_relations.py
checked entity_2, which never carries it in the benchmarks (ticket C2); that
behaviour is kept as mode "entity_2" so both conditions can be reported.

A marker counts only where it opens the mention, optionally after "or", "and"
or "but", and "if not" only where punctuation or the end of the mention
follows it. A marker anywhere in the text used to count: "elsewhere" fired
the rule as a substring, "asks someone else" as a whole word, and "If not
already registered", which is a condition, not the branch that answers one.

The cues live here only. finder3 merges an else-marker gateway into the
decision before it with `is_else_marker`, the same match with the further
condition that nothing but punctuation follows the marker.
"""
import re

FALSE_BRANCH_MARKERS = ("otherwise", "else", "if not")
# may precede the marker: "Or else, the clerk archives it"
LEADING_CONJUNCTIONS = ("or", "and", "but")
# a cue that is a marker only when nothing but punctuation follows it: "If
# not," answers a decision, "If not already registered" states a new one
STANDALONE_MARKERS = ("if not",)
MODES = ("entity_1", "entity_2", "both", "off")


def _cue(marker):
    pattern = r"\s+".join(map(re.escape, marker.split()))
    if marker in STANDALONE_MARKERS:
        pattern += r"(?=\s*(?:[,.;:!?)]|$))"
    return pattern


MARKER = re.compile(r"^\s*(?:(?:" + "|".join(LEADING_CONJUNCTIONS) + r")\s+)?"
                    r"(?:" + "|".join(map(_cue, FALSE_BRANCH_MARKERS)) + r")\b", re.I)
TRAILING_PUNCTUATION = " \t\n,.:;-"


def has_marker(text):
    """Whether an else-marker opens this mention."""
    return bool(MARKER.match(text or ""))


def is_else_marker(text):
    """Whether this mention is an else-marker and nothing more ("Otherwise,",
    "Or else"), as opposed to one that opens a step or a new decision."""
    match = MARKER.match(text or "")
    return bool(match) and not text[match.end():].strip(TRAILING_PUNCTUATION)


def false_branch_guardrail(relation, entity_1, entity_2, mode="entity_1"):
    if mode not in MODES:
        raise ValueError(f"unknown guardrail mode {mode!r}; expected one of {MODES}")
    if relation != "SEQUENCE" or mode == "off":
        return relation
    checked = {"entity_1": [entity_1], "entity_2": [entity_2], "both": [entity_1, entity_2]}[mode]
    return "FALSE_BRANCH" if any(has_marker(t) for t in checked) else relation
