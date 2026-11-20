import re

import pytest

from text2bpmn import prompts


def flat(text):
    """One line, single spaces: the wrapping of the prompt is not the point."""
    return re.sub(r"\s+", " ", text).strip()


def test_the_published_prompt_is_the_one_behind_the_published_numbers():
    """It is pinned: Table 3, the guardrail replay and the case studies were
    all produced with this exact text, so a silent edit invalidates them."""
    assert prompts.digest(prompts.PUBLISHED) == prompts.PUBLISHED_SHA256


def test_the_published_prompt_still_states_sequence_backwards():
    """The defect the revision exists to fix. If this ever fails, the published
    text has been edited and the arm comparison no longer means what it says."""
    assert "SEQUENCE: A follows B chronologically" in flat(prompts.PUBLISHED)


def test_the_table3_prompt_is_the_one_behind_table3():
    """benchmark_relations.py kept its own copy of the signature; that copy, not
    PUBLISHED, produced Table 3 and the guardrail replay."""
    assert prompts.digest(prompts.TABLE3) == prompts.TABLE3_SHA256
    assert "5. PARALLEL: Events happen simultaneously." in prompts.TABLE3
    assert "Meantime" not in prompts.TABLE3


def test_the_default_prompt_differs_from_the_published_one_only_in_rule_1():
    assert prompts.DEFAULT_PROMPT == "corrected"
    changed = [(a, b) for a, b in zip(prompts.PUBLISHED.splitlines(), prompts.CORRECTED.splitlines())
               if a != b]
    assert [(flat(a), flat(b)) for a, b in changed] == [
        ("1. SEQUENCE: A follows B chronologically.", "1. SEQUENCE: B follows A chronologically.")]


def test_the_pipeline_signature_carries_the_named_prompt():
    """DSPy dedents a signature's instructions, as it did the old docstring."""
    import inspect
    from text2bpmn.finder3 import relation_signature
    for name, text in prompts.PROMPTS.items():
        assert relation_signature(name).instructions == inspect.cleandoc(text)


def test_the_revision_states_the_direction_the_pipeline_actually_uses():
    assert "node_B happens after node_A" in flat(prompts.REVISED)
    assert "node_A appears before node_B" in flat(prompts.REVISED)


def test_the_revision_gives_the_model_somewhere_to_go():
    assert "closest one" in flat(prompts.REVISED)
    assert "Do not invent a label that is not in the list" in flat(prompts.REVISED)


def test_every_prompt_names_all_five_labels():
    for name, text in prompts.PROMPTS.items():
        for label in ("SEQUENCE", "CONDITION_DEF", "TRUE_BRANCH",
                      "FALSE_BRANCH", "PARALLEL"):
            assert label in text, f"{label} missing from {name}"


def test_the_demonstrations_are_the_ten_in_the_repository():
    examples = prompts.load_demonstrations()
    assert len(examples) == 10
    assert sorted(e.relation for e in examples) == sorted(
        ["SEQUENCE", "CONDITION_DEF", "TRUE_BRANCH", "FALSE_BRANCH", "PARALLEL"] * 2)


def test_missing_or_malformed_demonstrations_stop_the_run(tmp_path):
    with pytest.raises(FileNotFoundError):
        prompts.load_demonstrations(tmp_path / "absent.jsonl")
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"text": "a", "entity_1": "b", "entity_2": "c", "label": "SEQUENCE"}\n{"text": "no labels"}\n')
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        prompts.load_demonstrations(bad)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n")
    with pytest.raises(ValueError):
        prompts.load_demonstrations(empty)


def test_the_pipeline_will_not_start_without_its_demonstrations(tmp_path, monkeypatch):
    """It used to fall back to zero-shot and carry on."""
    from text2bpmn.finder3 import BPMNHybridExtractor
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="benchmark_unseen.jsonl"):
        BPMNHybridExtractor(ner_model_path=None)
