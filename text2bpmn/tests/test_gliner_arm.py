"""The GLiNER arm: sentence-by-sentence spans, their injection, and its guard."""
import sys
from types import SimpleNamespace

import pytest

from text2bpmn import gliner_spans, run_gliner_arm


def test_sentences_keep_their_offsets_and_split_only_at_a_full_stop_before_space():
    text = "  The clerk checks 2.5 kg, e.g. the box. Then he files it!  Done?"
    spans = gliner_spans.sentences(text)
    assert [text[s:e] for s, e in spans] == ["The clerk checks 2.5 kg, e.g.", "the box.",
                                            "Then he files it!", "Done?"]


def test_a_text_without_a_full_stop_is_one_sentence():
    assert gliner_spans.sentences("no stop here") == [(0, 12)]
    assert gliner_spans.sentences("   ") == []


class FakeModel:
    """Finds every word "checks" in a sentence, with a fixed score."""
    config = SimpleNamespace(max_len=4)

    def __init__(self):
        self.asked = []

    def predict_entities(self, piece, labels, threshold):
        self.asked.append(piece)
        at = piece.find("checks")
        return [] if at < 0 else [{"start": at, "end": at + 6, "label": "Activity", "score": 0.9}]


def test_spans_are_found_per_sentence_and_shifted_into_the_whole_text():
    text = "The clerk checks the form. Then the manager checks it again today."
    model = FakeModel()
    spans, too_long = gliner_spans.predict(model, text)
    assert model.asked == ["The clerk checks the form.", "Then the manager checks it again today."]
    assert [text[s["start"]:s["end"]] for s in spans] == ["checks", "checks"]
    assert too_long == 2  # both sentences are longer than the fake model's four words


def test_injection_keeps_the_spans_at_or_above_the_threshold():
    document = {"text": "abc", "spans": [{"start": 0, "end": 1, "label": "Actor", "score": 0.85},
                                         {"start": 1, "end": 2, "label": "Actor", "score": 0.84}]}
    injected = run_gliner_arm.injected(document, 0.85)
    assert injected["text"] == "abc" and [s["score"] for s in injected["spans"]] == [0.85]
    assert "one sentence at a time" in injected["source"]


def test_the_threshold_is_the_one_chosen_on_dev():
    assert run_gliner_arm.threshold() == 0.85


def test_run_one_hands_injected_spans_to_the_pipeline(tmp_path):
    from text2bpmn.checks.pilot_run import run_one

    seen = {}

    class Extractor:
        config = SimpleNamespace(ontology_out="")
        run_record = {"config": {}}

        def process_text(self, text, entities=None):
            seen["entities"] = entities
            raise RuntimeError("stop here")

    record = run_one(Extractor(), "doc", "some text", tmp_path / "doc", entities={"text": "t", "spans": []})
    assert seen["entities"] == {"text": "t", "spans": []}
    assert record["status"] == "failed"


def test_a_real_run_refuses_a_tree_off_its_tag(monkeypatch, tmp_path):
    monkeypatch.setattr(run_gliner_arm, "GLINER_MODEL", str(tmp_path))
    monkeypatch.setenv("GLINER_PYTHON", sys.executable)
    monkeypatch.setattr(run_gliner_arm, "_git_state",
                        lambda: {"commit": "x", "describe": "revision-final", "dirty": False})
    monkeypatch.setattr(sys, "argv", ["run_gliner_arm"])
    with pytest.raises(SystemExit, match="exactly at revision-final-3"):
        run_gliner_arm.main()
