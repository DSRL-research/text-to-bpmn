import json
from collections import Counter

import pytest
import spacy

from text2bpmn.finder3 import BPMNHybridExtractor
from text2bpmn.relation_parsing import UNKNOWN, ParseFailureLog
from text2bpmn.run_config import RunConfig


@pytest.fixture(scope="module")
def extractor():
    """Extractor without the NER, coreference and LLM models: exercises only
    the structuring logic of the pairwise mode (the method as submitted; the
    default is decisions4 since revision-final-3). With no LLM, relation calls
    return UNKNOWN."""
    x = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    x.dspy_predictor = None
    x.relation_log = ParseFailureLog()
    x.config = RunConfig(relation_mode="pairs")
    x.nlp_validator = spacy.load("en_core_web_sm")
    return x


def entities(*spans, text=None):
    """NER-style entities. With `text`, offsets are the real positions in it."""
    out, pos = [], 0
    for group, word in spans:
        if text is not None:
            start = text.index(word, pos)
        else:
            start = pos
        out.append({"entity_group": group, "word": word, "start": start, "end": start + len(word)})
        pos = start + len(word) + (0 if text is None else 1)
    return out


@pytest.mark.parametrize("span, expected", [
    ("the officer performs a credit check", "Performs a credit check"),  # verbal: trimmed to the verb
    ("##risk assessment.", "Risk assessment"),                            # nominal: kept, cleaned
    ("shipping", "Shipping"),
    ("the", None),                                                        # neither verb nor noun
    ("ti", None),                                                         # word-piece fragment
])
def test_activity_validation(extractor, span, expected):
    assert extractor._clean_and_validate_activity(span) == expected


def test_rejected_activities_do_not_become_tasks(extractor):
    data = extractor._structure_process_data(
        entities(("Activity", "risk assessment"), ("Activity", "the"), ("Activity", "approves the loan")),
        "risk assessment the approves the loan")
    tasks = [e["name"] for e in data["elements"] if e["type"] == "task"]
    assert tasks == ["Risk assessment", "Approves the loan"]


def test_further_specification_becomes_metadata_of_nearest_activity(extractor):
    data = extractor._structure_process_data(
        entities(("Further Specification", "for the loan"), ("Activity", "performs a credit check"),
                 ("Further Specification", "on the applicant"), ("Activity", "approves the loan")),
        "for the loan performs a credit check on the applicant approves the loan")
    tasks = {e["name"]: e["metadata"] for e in data["elements"] if e["type"] == "task"}
    # none precedes the first span, so it goes to the next activity
    assert tasks == {"Performs a credit check": ["For the loan", "On the applicant"], "Approves the loan": []}


def test_branch_target_reached_again_is_not_duplicated(extractor, monkeypatch):
    # "rejects the application" is a branch target of the gateway but does not
    # directly follow it, so the main loop reaches it a second time.
    def relation(context, a, b):
        return "TRUE_BRANCH" if (a["word"], b["word"]) == ("If eligible", "rejects the application") else "SEQUENCE"
    monkeypatch.setattr(extractor, "_predict_relation", relation)
    data = extractor._structure_process_data(
        entities(("XOR Gateway", "If eligible"), ("Activity", "prepares the pack"),
                 ("Activity", "sends the pack"), ("Activity", "rejects the application")),
        "If eligible prepares the pack sends the pack rejects the application")
    ids = [e["id"] for e in data["elements"]]
    assert len(ids) == len(set(ids))


def test_pipeline_guardrail_labels_the_edge_leaving_the_marker(extractor, monkeypatch):
    # The model says SEQUENCE everywhere; only the guardrail can create FALSE_BRANCH.
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "SEQUENCE")
    data = extractor._structure_process_data(
        entities(("Activity", "sends the pack"), ("XOR Gateway", "Otherwise"),
                 ("Activity", "rejects the application")),
        "sends the pack Otherwise rejects the application")
    names = {e["id"]: e["name"] for e in data["elements"]}
    no_edges = {(names[f["source"]], names[f["target"]]) for f in data["flows"] if f.get("name") == "No"}
    assert no_edges == {("Otherwise", "Rejects the application")}


def test_structured_output_is_json_serializable(extractor):
    data = extractor._structure_process_data(
        entities(("Actor", "The Clerk"), ("Activity", "checks the order"),
                 ("Actor", "The Manager"), ("Activity", "approves the order")),
        "The Clerk checks the order. The Manager approves the order.")
    assert data["participants"] == sorted(data["participants"])
    assert {"The Clerk", "The Manager"} <= set(data["participants"])
    json.dumps({"structured_data": data})


class _Answer:
    def __init__(self, relation):
        self.relation = relation


@pytest.mark.parametrize("predictor, expected, logged", [
    (lambda **kw: _Answer("**FALSE_BRANCH**"), "FALSE_BRANCH", None),
    (lambda **kw: _Answer("I cannot tell"), UNKNOWN, {"raw_output": "I cannot tell", "error": None}),
    (lambda **kw: (_ for _ in ()).throw(ConnectionError("ollama down")), UNKNOWN,
     {"raw_output": None, "error": "ollama down"}),
    (None, UNKNOWN, {"raw_output": None, "error": "no LLM predictor configured"}),
])
def test_parse_failures_are_unknown_and_logged(predictor, expected, logged):
    x = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    x.dspy_predictor, x.relation_log, x.config = predictor, ParseFailureLog(), RunConfig(relation_mode="pairs")
    assert x._predict_relation("ctx", {"word": "Otherwise"}, {"word": "rejects"}) == expected
    records = x.relation_log.summary()["records"]
    assert records == ([] if logged is None else [{"node_A": "Otherwise", "node_B": "rejects", **logged}])


def _stub(calls, labels=("SEQUENCE", "TRUE_BRANCH", "FALSE_BRANCH", "CONDITION_DEF")):
    """Deterministic stand-in for the LLM, recording the pairs it is asked about."""
    def predict(context, node_A, node_B):
        calls.append((node_A, node_B))
        return type("P", (), {"relation": labels[hash((node_A, node_B)) % len(labels)]})()
    return predict


def _normalise(data):
    ids = {e["id"]: f"{e['type']}#{i}" for i, e in enumerate(data["elements"])}
    return ([{**e, "id": ids[e["id"]]} for e in data["elements"]],
            sorted((ids.get(f["source"]), ids.get(f["target"]), f.get("name", "")) for f in data["flows"]))


CASE = (entities(("XOR Gateway", "If the order is urgent"), ("Activity", "ships the order"),
                 ("Activity", "packs the order"), ("Actor", "The Clerk"),
                 ("Activity", "sends an invoice"), ("XOR Gateway", "Otherwise"),
                 ("Activity", "cancels the order"), ("Activity", "notifies the customer")),
        "If the order is urgent ships the order packs the order The Clerk sends an invoice "
        "Otherwise cancels the order notifies the customer")


def test_skipping_unused_pairs_does_not_change_the_structure(extractor, monkeypatch):
    """Without a PARALLEL answer, a skipped pair could not have changed the model."""
    original_filter = type(extractor)._relation_needed

    def run(ask_every_pair):
        calls = []
        # disable the pre-filter itself, rather than the gateway types it reads,
        # which the branch patterns and CONDITION_DEF also use
        monkeypatch.setattr(extractor, "_relation_needed",
                            (lambda *a, **k: True) if ask_every_pair
                            else (lambda *a, **k: original_filter(extractor, *a, **k)))
        extractor.dspy_predictor = _stub(calls)  # never answers PARALLEL
        extractor.relation_log = ParseFailureLog()
        monkeypatch.setattr(extractor, "config", RunConfig(relation_mode="pairs", parallel_detection="off"))
        data = extractor._structure_process_data([dict(e) for e in CASE[0]], CASE[1])
        return len(calls), extractor.relation_log.summary()["skipped"], _normalise(data)

    before_calls, before_skipped, before = run(True)  # predict every pair
    after_calls, after_skipped, after = run(False)
    extractor.dspy_predictor = None
    assert (before_skipped, after_skipped) == (0, before_calls - after_calls)
    assert after_calls < before_calls
    assert after == before


PARALLEL_TEXT = ("The warehouseman packs the goods. In parallel, the clerk prints the invoice "
                 "and the driver loads the van. Finally the manager closes the order.")
PARALLEL_ENTITIES = entities(("Activity", "packs the goods"), ("Activity", "prints the invoice"),
                             ("Activity", "loads the van"), ("Activity", "closes the order"),
                             text=PARALLEL_TEXT)


def test_parallel_relations_build_a_block_between_split_and_join(extractor, monkeypatch):
    monkeypatch.setattr(extractor, "config", RunConfig(relation_mode="pairs", parallel_detection="cues"))
    peers = {"prints the invoice", "loads the van"}
    monkeypatch.setattr(extractor, "_predict_relation",
                        lambda context, a, b: "PARALLEL" if b["word"] in peers else "SEQUENCE")
    data = extractor._structure_process_data([dict(e) for e in PARALLEL_ENTITIES], PARALLEL_TEXT)
    names = {e["id"]: e["name"] or e["type"] for e in data["elements"]}
    gateways = [e for e in data["elements"] if e["type"] == "parallelGateway"]
    assert len(gateways) == 2, "a split and a join"
    split, join = (g["id"] for g in gateways)
    members = {"Packs the goods", "Prints the invoice", "Loads the van"}
    assert {names[f["target"]] for f in data["flows"] if f["source"] == split} == members
    assert {names[f["source"]] for f in data["flows"] if f["target"] == join} == members
    # the block is left through the join, and no peer is linked a second time
    assert [names[f["target"]] for f in data["flows"] if f["source"] == join] == ["Closes the order"]
    ids = [e["id"] for e in data["elements"]]
    assert len(ids) == len(set(ids))


def test_parallel_block_is_well_formed_bpmn(extractor, monkeypatch):
    from text2bpmn.structure import problems, validate
    monkeypatch.setattr(extractor, "config", RunConfig(relation_mode="pairs", parallel_detection="cues"))
    peers = {"prints the invoice", "loads the van"}
    monkeypatch.setattr(extractor, "_predict_relation",
                        lambda context, a, b: "PARALLEL" if b["word"] in peers else "SEQUENCE")
    data = extractor._structure_process_data([dict(e) for e in PARALLEL_ENTITIES], PARALLEL_TEXT)
    assert problems(validate(data)) == []


@pytest.mark.parametrize("mode, text, asked", [
    ("cues", PARALLEL_TEXT, True),
    ("cues", "The clerk packs the goods. Then the clerk prints the invoice.", False),
    ("all", "The clerk packs the goods. Then the clerk prints the invoice.", True),
    ("off", PARALLEL_TEXT, False),
])
def test_when_two_activities_are_asked_about(extractor, monkeypatch, mode, text, asked):
    monkeypatch.setattr(extractor, "config", RunConfig(relation_mode="pairs", parallel_detection=mode))
    first, second = entities(("Activity", "packs the goods"), ("Activity", "prints the invoice"),
                             text=text if "packs the goods" in text else None)
    assert extractor._relation_needed(dict(first, type="task"), dict(second, type="task"), text) is asked


CONDITION_TEXT = "If the applicant is eligible the officer approves the loan otherwise rejects it"


def test_condition_is_folded_into_its_gateway(extractor, monkeypatch):
    monkeypatch.setattr(extractor, "_predict_relation",
                        lambda context, a, b: "CONDITION_DEF" if b["word"] == "the applicant is eligible"
                        else "SEQUENCE")
    # NER split the decision into two gateway spans; the relation says the second
    # states the condition of the first
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("XOR Gateway", "If"), ("XOR Gateway", "the applicant is eligible"),
                                   ("Activity", "approves the loan"), text=CONDITION_TEXT)],
        CONDITION_TEXT)
    gateways = [e for e in data["elements"] if e["type"] == "exclusiveGateway"]
    assert [g["name"] for g in gateways] == ["If the applicant is eligible"]
    assert "the applicant is eligible" not in [e["name"].lower() for e in data["elements"] if e["type"] == "task"]
    targets = {f["target"] for f in data["flows"] if f["source"] == gateways[0]["id"]}
    assert {e["name"] for e in data["elements"] if e["id"] in targets} == {"Approves the loan"}


def test_condition_already_in_the_gateway_label_is_not_repeated(extractor, monkeypatch):
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "CONDITION_DEF")
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("XOR Gateway", "If the applicant is eligible"),
                                   ("Activity", "the applicant is eligible"))],
        CONDITION_TEXT)
    names = [e["name"] for e in data["elements"] if e["type"] == "exclusiveGateway"]
    assert names == ["If the applicant is eligible"]


def test_condition_relation_from_a_task_changes_nothing(extractor, monkeypatch):
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "CONDITION_DEF")
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("Activity", "checks the score"), ("Activity", "approves the loan"),
                                   text="checks the score approves the loan")],
        "checks the score approves the loan")
    assert [e["name"] for e in data["elements"] if e["type"] == "task"] == ["Checks the score", "Approves the loan"]


def test_qualifying_labels_become_activity_metadata(extractor):
    """Further Specification describes its activity. Activity Data is different:
    it completes the label, see the test below."""
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("Activity", "checks the order"),
                                   ("Further Specification", "for completeness"),
                                   ("Activity", "ships the order"))],
        "checks the order for completeness ships the order")
    tasks = {e["name"]: e["metadata"] for e in data["elements"] if e["type"] == "task"}
    assert tasks == {"Checks the order": ["For completeness"], "Ships the order": []}


@pytest.mark.parametrize("label", ["TASK_INFO", "TASK", "AGENT", "CONDITION", "Parallel Gateway"])
def test_labels_outside_the_pet_scheme_stop_the_run(label):
    """They used to be accepted, and one the code did not name became a task."""
    from text2bpmn.finder3 import check_labels
    with pytest.raises(ValueError, match="outside the PET scheme"):
        check_labels([{"entity_group": "Activity"}, {"entity_group": label}])


def test_injected_spans_with_an_unknown_label_are_refused(extractor):
    with pytest.raises(ValueError, match="TASK_INFO"):
        extractor.process_text("x", entities={"text": "for the loan",
                                              "spans": [{"start": 0, "end": 12, "label": "TASK_INFO"}]})


def test_condition_specification_joins_the_gateway_before_it(extractor):
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("XOR Gateway", "If"), ("Condition Specification", "the order is urgent"),
                                   ("Activity", "ships the order"))],
        "If the order is urgent ships the order")
    gateways = [e["name"] for e in data["elements"] if e["type"] == "exclusiveGateway"]
    assert gateways == ["If the order is urgent"]
    assert "the order is urgent" not in [e["name"].lower() for e in data["elements"] if e["type"] == "task"]


def test_condition_without_a_gateway_becomes_one(extractor):
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("Condition Specification", "the order is urgent"),
                                   ("Activity", "ships the order"))],
        "the order is urgent ships the order")
    assert [e["name"] for e in data["elements"] if e["type"] == "exclusiveGateway"] == ["The order is urgent"]


def test_and_gateway_label_gives_a_parallel_gateway(extractor, monkeypatch):
    monkeypatch.setattr(extractor, "_predict_relation",
                        lambda context, a, b: "PARALLEL" if b["word"] == "prints the invoice" else "SEQUENCE")
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("AND Gateway", "In parallel"), ("Activity", "packs the goods"),
                                   ("Activity", "prints the invoice"))],
        "In parallel packs the goods prints the invoice")
    assert any(e["type"] == "parallelGateway" for e in data["elements"])


def test_an_actor_between_and_branches_does_not_rewire_the_block(extractor, monkeypatch):
    """R2-3, R2-21: the second branch sits behind an Actor mention. It used to be
    processed again, and the flow then left the block from it, not the join."""
    from text2bpmn.structure import validate
    text = "In parallel the clerk prints the invoice and the driver loads the van. Then closes the order."
    spans = entities(("AND Gateway", "In parallel"), ("Activity", "prints the invoice"),
                     ("Actor", "the driver"), ("Activity", "loads the van"),
                     ("Activity", "closes the order"), text=text)
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b:
                        "PARALLEL" if b["word"] in ("prints the invoice", "loads the van") else "SEQUENCE")
    data = extractor._structure_process_data([dict(e) for e in spans], text)
    names = {e["id"]: e["name"] for e in data["elements"]}
    into_close = [names[f["source"]] for f in data["flows"] if names[f["target"]] == "Closes the order"]
    assert into_close == ["+"], "the step after the block follows the join, and only the join"
    p = validate(data)
    assert sorted(n.kind for n in p.nodes.values() if "Gateway" in n.kind) == ["parallelGateway"] * 2


def test_activity_data_completes_the_task_label(extractor):
    """PET marks the verb as the Activity and its object as Activity Data."""
    text = "Prepared the acceptance pack for the applicant. Sent the letter."
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("Activity", "Prepared"), ("Activity Data", "the acceptance pack"),
                                   ("Activity Data", "for the applicant"),
                                   ("Activity", "Sent"), ("Activity Data", "the letter"), text=text)],
        text)
    tasks = {e["name"]: e["metadata"] for e in data["elements"] if e["type"] == "task"}
    assert tasks == {"Prepared the acceptance pack": ["For the applicant"], "Sent the letter": []}


def test_further_specification_stays_documentation(extractor):
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("Activity", "Checked"), ("Further Specification", "carefully"))],
        "Checked carefully")
    tasks = {e["name"]: e["metadata"] for e in data["elements"] if e["type"] == "task"}
    assert tasks == {"Checked": ["Carefully"]}


def test_object_before_its_verb_is_attached_to_that_verb(extractor):
    """Passive voice: "the acceptance pack is prepared" puts the object first."""
    text = "the application is rejected, otherwise the acceptance pack is prepared"
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("Activity", "rejected"), ("Activity Data", "the acceptance pack"),
                                   ("Activity", "prepared"), text=text)],
        text)
    assert {e["name"] for e in data["elements"] if e["type"] == "task"} == \
           {"Rejected", "Prepared the acceptance pack"}


def test_gateway_takes_one_condition_and_documents_the_rest(extractor):
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("XOR Gateway", "If"), ("Condition Specification", "the order is urgent"),
                                   ("Condition Specification", "and the customer is premium"))],
        "If the order is urgent and the customer is premium")
    gateways = [e for e in data["elements"] if e["type"] == "exclusiveGateway"]
    assert [g["name"] for g in gateways] == ["If the order is urgent"]
    assert gateways[0]["metadata"] == ["And the customer is premium"]


def test_condition_relation_never_swallows_an_activity(extractor, monkeypatch):
    """The LLM may call an activity the gateway's condition; NER says it is a
    step, and a step must stay a task."""
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "CONDITION_DEF")
    text = "If the application passes checks credit history assesses risk"
    data = extractor._structure_process_data(
        [dict(e) for e in entities(("XOR Gateway", "If the application passes"),
                                   ("Activity", "checks credit history"),
                                   ("Activity", "assesses risk"), text=text)],
        text)
    assert {e["name"] for e in data["elements"] if e["type"] == "task"} == \
           {"Checks credit history", "Assesses risk"}
    assert [e["name"] for e in data["elements"] if e["type"] == "exclusiveGateway"] == \
           ["If the application passes"]


LANE_TEXT = ("The appraisal of the property is carried out by a property appraiser. "
             "A financial officer checks the credit history.")
LANE_ENTITIES = entities(("Activity Data", "The appraisal of the property"), ("Activity", "carried"),
                         ("Actor", "a property appraiser"),
                         ("Actor", "A financial officer"), ("Activity", "checks"),
                         ("Activity Data", "the credit history"), text=LANE_TEXT)


def test_lane_comes_from_the_actor_in_the_same_sentence(extractor):
    """PET names the actor after the verb as often as before it, so the lane
    cannot be the actor last seen in reading order (reviewer R2.18)."""
    data = extractor._structure_process_data([dict(e) for e in LANE_ENTITIES], LANE_TEXT)
    assert {e["name"]: e["lane"] for e in data["elements"] if e["type"] == "task"} == \
           {"Carried the appraisal of the property": "A property appraiser",
            "Checks the credit history": "A financial officer"}


def test_the_model_is_asked_about_composed_labels_not_bare_verbs(extractor, monkeypatch):
    """An activity's span is the bare verb; its object comes from a separate
    Activity Data span. The pair the model is asked about carries both."""
    calls = []
    monkeypatch.setattr(extractor, "dspy_predictor", _stub(calls))
    monkeypatch.setattr(extractor, "relation_log", ParseFailureLog())
    extractor._structure_process_data([dict(e) for e in LANE_ENTITIES], LANE_TEXT)
    assert ("Carried the appraisal of the property", "Checks the credit history") in calls
    assert not any(side in ("Carried", "Checks") for pair in calls for side in pair)


def test_a_gateway_span_is_not_retyped_by_a_branch_relation(extractor, monkeypatch):
    """Being named as a branch's target says which way the branch runs, not that
    the marker NER read ("if", "In case of") is a step."""
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "FALSE_BRANCH")
    data = extractor._structure_process_data([dict(e) for e in CASE[0]], CASE[1])
    assert {e["name"]: e["type"] for e in data["elements"]}["If the order is urgent"] == \
           "exclusiveGateway"


def test_an_else_marker_is_not_a_node_and_its_branch_leaves_the_decision(extractor, monkeypatch):
    """"Otherwise" labels the branch out of the decision before it; it is neither
    a step nor a second decision."""
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "FALSE_BRANCH")
    data = extractor._structure_process_data([dict(e) for e in CASE[0]], CASE[1])
    names = {e["id"]: e["name"] for e in data["elements"]}
    assert "Otherwise" not in names.values()
    assert ("If the order is urgent", "Cancels the order") in \
           {(names[f["source"]], names[f["target"]]) for f in data["flows"] if f.get("name") == "No"}


def test_every_relation_decision_is_recorded(extractor, monkeypatch):
    """The log kept only failures, so a missing construct could not be traced to
    the pair that was asked (or never asked) about it."""
    calls = []
    monkeypatch.setattr(extractor, "dspy_predictor", _stub(calls))
    monkeypatch.setattr(extractor, "relation_log", ParseFailureLog())
    monkeypatch.setattr(extractor, "config", RunConfig(relation_mode="pairs", parallel_detection="cues"))
    extractor._structure_process_data([dict(e) for e in CASE[0]], CASE[1])
    decisions = extractor.relation_log.summary()["decisions"]
    assert [(d["node_A"], d["node_B"]) for d in decisions if d["source"] != "not_asked"] == calls
    assert [d for d in decisions if d["source"] == "not_asked"], "skipped pairs are recorded too"
    assert all(d["label"] == "FALSE_BRANCH" and d["model_label"] != "FALSE_BRANCH"
               for d in decisions if d["source"] == "guardrail")


def test_entity_spans_are_extended_to_whole_words():
    """Token classification cut "clarifies" into "c" + "##ifies", which merge to
    "cifies": a span that starts or ends inside a word is read from the text."""
    text = "the secretary clarifies who will do the shipping"
    spans = [{"entity_group": "Activity", "word": "cifies", "start": 15, "end": 23},
             {"entity_group": "Actor", "word": "the secretary", "start": 0, "end": 13}]
    BPMNHybridExtractor._snap_to_words(spans, text)
    assert [(e["word"], e["start"], e["end"]) for e in spans] == \
           [("clarifies", 14, 23), ("the secretary", 0, 13)]


BRANCH_TEXT = ("If you have large amounts the secretary invites three companies and she selects one. "
               "Otherwise normal post shipment is used.")
BRANCH_ENTITIES = entities(("XOR Gateway", "If you have large amounts"),
                           ("Activity", "invites three companies"), ("Activity", "selects one"),
                           ("XOR Gateway", "Otherwise"), ("Activity", "normal post shipment is used"),
                           text=BRANCH_TEXT)


def _edges(data):
    names = {e["id"]: e["name"] for e in data["elements"]}
    return [(names[f["source"]], names[f["target"]], f.get("name", "")) for f in data["flows"]]


def test_an_exclusive_split_has_one_flow_per_outcome(extractor, monkeypatch):
    """Two activities called the true branch are that branch in order, not two
    flows leaving the decision with the same label."""
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "TRUE_BRANCH")
    data = extractor._structure_process_data([dict(e) for e in BRANCH_ENTITIES], BRANCH_TEXT)
    edges = _edges(data)
    assert ("If you have large amounts", "Invites three companies", "Yes") in edges
    assert ("Invites three companies", "Selects one", "") in edges
    assert ("If you have large amounts", "Selects one", "Yes") not in edges


def test_a_branch_leaving_an_else_marker_is_the_false_branch(extractor, monkeypatch):
    """The marker introduces the false branch whichever label the model gives
    the pair, and the decision keeps one edge per target."""
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b: "TRUE_BRANCH")
    data = extractor._structure_process_data([dict(e) for e in BRANCH_ENTITIES], BRANCH_TEXT)
    edges = _edges(data)
    assert ("If you have large amounts", "Used", "No") in edges  # trimmed to its verb
    pairs = [(source, target) for source, target, _ in edges]
    assert len(pairs) == len(set(pairs)), f"duplicate edges: {pairs}"


def test_a_snapped_span_does_not_keep_its_punctuation(extractor):
    assert extractor._clean_name("two checks:") == "Two checks"


def split(extractor, text, span):
    start = text.index(span)
    pieces = extractor._post_process_split(
        [{"entity_group": "Activity", "word": span, "start": start, "end": start + len(span), "score": 1.0}])
    for p in pieces:
        assert text[p["start"]:p["end"]] == p["word"], "each piece carries its own offsets"
    return [(p["entity_group"], p["word"]) for p in pieces]


@pytest.mark.parametrize("span, expected", [
    ("Sends email. Otherwise rejected",
     [("Activity", "Sends email"), ("XOR Gateway", "Otherwise"), ("Activity", "rejected")]),
    ("Otherwise rejects the application",
     [("XOR Gateway", "Otherwise"), ("Activity", "rejects the application")]),
    ("is rejected, otherwise the pack is prepared",
     [("Activity", "is rejected"), ("XOR Gateway", "otherwise"), ("Activity", "the pack is prepared")]),
    ("Sends email. Files it", [("Activity", "Sends email"), ("Activity", "Files it")]),
    ("files it elsewhere", [("Activity", "files it elsewhere")]),
])
def test_an_else_marker_inside_an_activity_span_becomes_its_own_mention(extractor, span, expected):
    assert split(extractor, f"The clerk {span}. Done.", span) == expected


def test_a_recovered_else_marker_carries_the_false_branch(extractor, monkeypatch):
    """The marker used to vanish into "Rejected"; now the guardrail sees it and
    the branch leaves the decision labelled No."""
    text = "If the form is complete, the clerk files it. Otherwise rejects the form."
    spans = entities(("XOR Gateway", "If"), ("Condition Specification", "the form is complete"),
                     ("Activity", "files it"), ("Activity", "Otherwise rejects the form"), text=text)
    monkeypatch.setattr(extractor, "_predict_relation", lambda context, a, b:
                        "TRUE_BRANCH" if (a["word"], b["word"]) == ("If", "files it") else "SEQUENCE")
    data = extractor._structure_process_data(extractor._post_process_split([dict(e) for e in spans]), text)
    names = {e["id"]: e["name"] for e in data["elements"]}
    branches = {(names[f["source"]], names[f["target"]], f.get("name")) for f in data["flows"]}
    assert ("If the form is complete", "Rejects the form", "No") in branches
    assert ("If the form is complete", "Files it", "Yes") in branches


@pytest.mark.parametrize("text, actor, expected", [
    # measured against PET's actor-recipient relations
    ("The clerk sends the invoice to the manager", "the manager", True),
    ("The clerk informs the manager", "the manager", True),      # 20 such cases in PET
    ("The clerk notifies the manager", "the manager", True),
    ("The clerk tells the manager", "the manager", True),
    # "from" precedes 4 performers in PET and no recipient, so it marks nothing
    ("The invoice is received from the manager", "the manager", False),
    ("The manager checks the invoice", "The manager", False),
])
def test_which_actors_are_only_recipients(extractor, text, actor, expected):
    span = {"start": text.index(actor), "end": text.index(actor) + len(actor)}
    assert extractor._is_recipient(span, text) is expected


LANE_BACK_TEXT = ("The financial officer reviews the application. "
                  "The credit history is then checked.")


def test_a_lane_may_come_from_the_sentence_before(extractor):
    """PET never puts the performer in a later sentence, and 26 of the 57
    activities the sentence-bounded rule could not reach have it in the one
    immediately before."""
    data = extractor._structure_process_data(
        entities(("Actor", "The financial officer"), ("Activity", "reviews"),
                 ("Activity Data", "the application"), ("Activity Data", "The credit history"),
                 ("Activity", "checked"), text=LANE_BACK_TEXT),
        LANE_BACK_TEXT)
    lanes = {e["name"]: e["lane"] for e in data["elements"] if e["type"] == "task"}
    assert lanes["Checked the credit history"] == "The financial officer"


def test_the_sentence_itself_still_wins(extractor):
    """The fallback applies only where the sentence has no actor of its own."""
    text = ("The financial officer reviews the application. "
            "The manager approves the application.")
    data = extractor._structure_process_data(
        entities(("Actor", "The financial officer"), ("Activity", "reviews"),
                 ("Actor", "The manager"), ("Activity", "approves"), text=text),
        text)
    lanes = {e["name"]: e["lane"] for e in data["elements"] if e["type"] == "task"}
    assert lanes["Approves"] == "The manager"


def test_a_lane_is_not_taken_from_a_later_sentence(extractor):
    text = "The application is checked. The manager approves it."
    data = extractor._structure_process_data(
        entities(("Activity Data", "The application"), ("Activity", "checked"),
                 ("Actor", "The manager"), ("Activity", "approves"), text=text),
        text)
    checked = next(e for e in data["elements"] if e["name"].startswith("Checked"))
    assert checked["lane"] != "The manager"


def test_a_text_longer_than_512_tokens_is_read_to_its_end():
    """Past BERT's 512 tokens the recogniser used to return nothing, with no
    message: PET's four longest documents lost everything after the cut. Needs
    the real checkpoint, which is not in the repository."""
    from pathlib import Path
    from text2bpmn.finder3 import NER_MODEL_PATH
    if not Path(NER_MODEL_PATH).exists():
        pytest.skip("NER checkpoint not present")
    x = BPMNHybridExtractor(config=RunConfig(allow_no_llm=True, api_base="http://127.0.0.1:1"),
                            ner_model_path=NER_MODEL_PATH)
    steps = ["The clerk receives the order and checks the invoice.",
             "The warehouse worker packs the goods for the customer.",
             "The manager approves the shipment and signs the delivery note."]
    text = " ".join(steps * 20 + ["Finally, the secretary archives the contract."])
    assert len(x.ner_pipeline.tokenizer(text)["input_ids"]) > 512
    spans = x.ner_pipeline(text)
    last = max(spans, key=lambda e: e["end"])
    assert last["start"] > len(text) - 60, "a mention in the closing sentence"
    assert any(text[e["start"]:e["end"]].strip() == "archives" for e in spans)


# pilot-parallel-4 as the recogniser reads it, answered by the scripted pilot's rules
P4_TEXT = " ".join(open("text2bpmn/checks/pilot_texts/parallel-4.txt", encoding="utf-8").read().split())
P4_SPANS = [("Actor", "The officer"), ("Activity", "reviews"), ("Activity Data", "the loan application."),
            ("XOR Gateway", "If"), ("Condition Specification", "the applicant has a good credit score,"),
            ("Actor", "the officer"), ("Activity", "approves"), ("Activity Data", "the loan."),
            ("XOR Gateway", "Otherwise,"), ("Actor", "the officer"), ("Activity", "requests"),
            ("Activity Data", "a guarantor."), ("Actor", "the bank"), ("Activity", "prepares"),
            ("Activity Data", "the contract"), ("AND Gateway", "at the same"), ("Actor", "the notary"),
            ("Activity", "verifies"), ("Activity Data", "the documents."), ("Actor", "the officer"),
            ("Activity", "informs"), ("Actor", "the applicant.")]


def parallel_4(extractor, monkeypatch):
    from text2bpmn.checks.scripted_pilot import scripted_relation, sentence_at
    state = {"head": None}

    def scripted(context, a, b):
        first, state["head"] = state["head"] != a["id"], a["id"]
        return scripted_relation(a.get("clean_name") or a["word"], sentence_at(context, b.get("start")), first)[0]

    monkeypatch.setattr(extractor, "_predict_relation", scripted)
    return extractor._structure_process_data([dict(e) for e in entities(*P4_SPANS, text=P4_TEXT)], P4_TEXT)


def test_a_parallel_block_on_a_branch_target_takes_the_branch_into_its_split(extractor, monkeypatch):
    """Defect 3: a block built around a decision's branch target kept the branch
    edge into the task and added a second edge from the decision to the split,
    so the block's join waited for the branch not taken."""
    data = parallel_4(extractor, monkeypatch)
    kinds = {e["id"]: e["type"] for e in data["elements"]}
    decision = next(e["id"] for e in data["elements"] if (e.get("name") or "").startswith("If the applicant"))
    outcomes = {f.get("name"): kinds[f["target"]] for f in data["flows"] if f["source"] == decision}
    assert outcomes == {"Yes": "parallelGateway", "No": "parallelGateway"}
    into = Counter(f["target"] for f in data["flows"])
    assert not [i for i, k in kinds.items() if k == "task" and into[i] > 1], "no task entered twice"


def test_parallel_4_is_sound(extractor, monkeypatch, tmp_path):
    """Defect 4: the join after the two outcomes' blocks was typed by the
    nearest split on each path, parallel on both, though the paths part at the
    exclusive decision; the parallel join waited for both outcomes."""
    import pm4py
    from text2bpmn.bpmn_xml import to_xml
    from text2bpmn.structure import validate
    path = tmp_path / "parallel-4.bpmn"
    path.write_text(to_xml(validate(parallel_4(extractor, monkeypatch))), encoding="utf-8")
    net, im, fm = pm4py.convert_to_petri_net(pm4py.read_bpmn(str(path)))
    assert pm4py.check_soundness(net, im, fm)[0]
