"""Relation idea 2 (pairs2: a NONE answer, fewer pairs asked) and idea 1c."""
import pytest
import spacy

from text2bpmn import prompts
from text2bpmn.finder3 import (RELATION_LABELS, RELATION_LABELS_NONE, BPMNHybridExtractor, labels_for,
                               relation_schema, relation_signature)
from text2bpmn.relation_parsing import UNKNOWN, ParseFailureLog, parse_relation
from text2bpmn.run_config import RunConfig
from text2bpmn.tests.test_finder3 import entities


def extractor(mode):
    x = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    x.dspy_predictor = None
    x.config = RunConfig(relation_mode=mode)
    x.relation_log = ParseFailureLog(labels_for(x.config))
    x.nlp_validator = spacy.load("en_core_web_sm")
    return x


TEXT = ("The clerk checks the form and files the form. If the form is complete, the clerk sends it. "
        "Otherwise, the clerk returns it. The clerk then archives the case.")
SPANS = [("Actor", "The clerk"), ("Activity", "checks"), ("Activity Data", "the form"), ("Activity", "files"),
         ("Activity Data", "the form"), ("XOR Gateway", "If"), ("Condition Specification", "the form is complete"),
         ("Actor", "the clerk"), ("Activity", "sends"), ("XOR Gateway", "Otherwise"), ("Actor", "the clerk"),
         ("Activity", "returns"), ("Actor", "The clerk"), ("Activity", "archives"), ("Activity Data", "the case")]


def run(x, monkeypatch, answer):
    asked = []

    def predict(context, a, b):
        asked.append((a["clean_name"], b["clean_name"]))
        return x.relation_log.parse(answer(a, b), node_A=a["clean_name"], node_B=b["clean_name"])

    monkeypatch.setattr(x, "_predict_relation", predict)
    return x._structure_process_data(entities(*SPANS, text=TEXT), TEXT), asked


def test_pairs2_asks_neighbours_and_pairs_with_a_gateway_only(monkeypatch):
    _, asked = run(extractor("pairs2"), monkeypatch, lambda a, b: "NONE")
    _, all_pairs = run(extractor("pairs"), monkeypatch, lambda a, b: "SEQUENCE")
    assert ("Checks the form", "Files the form") in asked             # neighbours
    assert ("Checks the form", "Sends") not in asked                  # two steps apart, no gateway
    assert ("Checks the form", "If the form is complete") in asked     # a gateway
    assert ("Checks the form", "Sends") in all_pairs
    assert len(asked) < len(all_pairs)


def test_none_builds_no_branch_and_the_else_marker_guardrail_still_fires(monkeypatch):
    x = extractor("pairs2")
    data, _ = run(x, monkeypatch, lambda a, b: "NONE")
    decisions = x.relation_log.summary()["decisions"]
    assert any(d["source"] == "guardrail" and d["node_A"] == "Otherwise" and d["label"] == "FALSE_BRANCH"
               and d["model_label"] == "NONE" for d in decisions)
    assert all(d["label"] in ("NONE", "FALSE_BRANCH") for d in decisions if d["source"] != "not_asked")
    assert any(d["source"] == "not_asked" for d in decisions)


def test_the_as_submitted_mode_is_unchanged(monkeypatch):
    x = extractor("pairs")
    assert x.relation_log.labels == tuple(RELATION_LABELS) or list(x.relation_log.labels) == list(RELATION_LABELS)
    _, asked = run(x, monkeypatch, lambda a, b: "SEQUENCE")
    assert ("Checks the form", "Sends") in asked


def test_the_schema_parser_and_signature_of_pairs2_know_none():
    assert relation_schema(10, RELATION_LABELS_NONE)["properties"]["relation"]["enum"][-1] == "NONE"
    assert relation_schema(10)["properties"]["relation"]["enum"] == list(RELATION_LABELS)
    assert parse_relation("NONE", RELATION_LABELS_NONE) == "NONE"
    assert parse_relation("NONE") == UNKNOWN
    assert "NONE" in relation_signature("corrected_none", none=True).output_fields["relation"].json_schema_extra["desc"]


def test_the_none_prompt_is_the_corrected_one_with_a_sixth_rule():
    text = prompts.PROMPTS["corrected_none"]
    assert text.startswith(prompts.CORRECTED.rstrip())
    assert "6. NONE" in text


# --- idea 1c ------------------------------------------------------------------

AND_TEXT = "If the order is large, the clerk invites offers. In parallel, the clerk packs it. The clerk ships it."
AND_SPANS = [("XOR Gateway", "If"), ("Condition Specification", "the order is large"), ("Actor", "the clerk"),
             ("Activity", "invites"), ("Activity Data", "offers"), ("AND Gateway", "In parallel"),
             ("Actor", "the clerk"), ("Activity", "packs"), ("Actor", "The clerk"), ("Activity", "ships")]


@pytest.mark.parametrize("mode, listed, merges_at_a_parallel_gateway", [
    ("decisions2", ["Invites offers"], True),
    ("decisions3", ["Invites offers", "Packs", "Ships"], False)])
def test_1c_leaves_the_parallel_word_out_so_no_branches_meet_there(monkeypatch, mode, listed,
                                                                  merges_at_a_parallel_gateway):
    x = extractor(mode)
    seen = []

    def ask(context, decision, steps, lanes, kinds=None):
        seen.append([s["clean_name"] for s in steps])
        return ["yes"] + ["after"] * (len(steps) - 1)

    monkeypatch.setattr(x, "_ask_decision", ask)
    data = x._structure_process_data(entities(*AND_SPANS, text=AND_TEXT), AND_TEXT)
    assert seen == [listed]
    parallel = {e["id"] for e in data["elements"] if e["type"] == "parallelGateway"}
    into = [f for f in data["flows"] if f["target"] in parallel]
    assert (len(into) == 2) is merges_at_a_parallel_gateway
