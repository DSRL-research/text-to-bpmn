"""Parse the LLM's relation answer the same way in the pipeline and the
benchmark (ticket C7).

finder3.py returned SEQUENCE when the answer could not be parsed or the call
failed, and benchmark_relations.py returned UNKNOWN. Both now use
parse_relation, which returns UNKNOWN: a failure is never silently counted as
a sequence. ParseFailureLog counts every call and records each failure with
the model's raw output (or the error), so the failure rate can be reported.

It also records every decision, not only the failures: which pairs were asked,
what label came back, which pairs a guardrail overrode and which were never
asked. Why a construct is missing from a diagram is otherwise only answerable
by re-running the pipeline and reading its console output.
"""
import logging

from text2bpmn.relation_metrics import LABELS

UNKNOWN = "UNKNOWN"
log = logging.getLogger("text2bpmn.relations")


def parse_relation(raw, labels=LABELS):
    """Relation label named in the model's answer, or UNKNOWN. `labels`, in
    the order they are looked for: relation idea 2 adds NONE, last.

    Same steps as both originals: drop a "Prediction:" prefix and markdown
    bold; an exact label on the first line; else the first label (in LABELS
    order) named on the first line, then on any later line.
    """
    text = str(raw)
    if "Prediction:" in text:
        text = text.split("Prediction:")[-1]
    lines = text.replace("*", "").strip().split("\n")
    if lines[0].strip() in labels:
        return lines[0].strip()
    for line in lines:
        for label in labels:
            if label in line:
                return label
    return UNKNOWN


class ParseFailureLog:
    def __init__(self, labels=LABELS):
        self.labels = labels
        self.calls = 0
        self.skipped = 0
        self.failures = []
        self.decisions = []

    def skip(self, **pair):
        """A pair whose relation is never used, so no call is made (ticket C8)."""
        self.skipped += 1
        if pair:
            self._decide(pair, None, "not_asked")

    def parse(self, raw, **pair):
        self.calls += 1
        label = parse_relation(raw, self.labels)
        self._decide(pair, label, "llm" if label != UNKNOWN else "parse_failure")
        if label == UNKNOWN:
            self._fail(pair, raw_output=str(raw), error=None)
        return label

    def error(self, error, **pair):
        self.calls += 1
        self._decide(pair, UNKNOWN, "call_failed")
        self._fail(pair, raw_output=None, error=str(error))
        return UNKNOWN

    def answered(self, label, **pair):
        """A call whose answer is not one relation label: a decision question's
        labels for its steps (text2bpmn/decisions.py)."""
        self.calls += 1
        self._decide(pair, label, "llm")
        return label

    def guardrail(self, label, **pair):
        """A symbolic rule overrode the model's answer for this pair."""
        for record in reversed(self.decisions):
            if all(record.get(k) == v for k, v in pair.items()):
                record["model_label"], record["label"] = record["label"], label
                record["source"] = "guardrail"
                return label
        self._decide(pair, label, "guardrail")
        return label

    def _decide(self, pair, label, source):
        self.decisions.append({**pair, "label": label, "source": source})

    def _fail(self, pair, **detail):
        record = {**pair, **detail}
        self.failures.append(record)
        log.warning("relation parse failure %d/%d: %s", len(self.failures), self.calls, record)

    def summary(self):
        return {"calls": self.calls, "skipped": self.skipped, "failures": len(self.failures),
                "rate": len(self.failures) / self.calls if self.calls else 0.0,
                "records": self.failures, "decisions": self.decisions}
