from pathlib import Path

import pytest

from text2bpmn.relation_metrics import LABELS, compute, load_dataset, predictions_from_report

REPO = Path(__file__).resolve().parents[2]


def test_per_class_values_follow_labels_not_alphabetical_order():
    # TRUE_BRANCH sorts last alphabetically but is second in LABELS.
    y_true = ["TRUE_BRANCH"] * 4 + ["CONDITION_DEF"] * 2
    y_pred = ["TRUE_BRANCH"] * 3 + ["CONDITION_DEF"] + ["CONDITION_DEF"] * 2
    res = compute(y_true, y_pred)
    assert res["per_class"]["TRUE_BRANCH"]["recall"] == pytest.approx(0.75)
    assert res["per_class"]["TRUE_BRANCH"]["precision"] == pytest.approx(1.0)
    assert res["per_class"]["CONDITION_DEF"]["precision"] == pytest.approx(2 / 3)
    row = res["confusion_matrix"][LABELS.index("TRUE_BRANCH")]
    assert row[LABELS.index("TRUE_BRANCH")] == 3 and row[LABELS.index("CONDITION_DEF")] == 1


def test_unknown_predictions_are_errors_with_their_own_column():
    res = compute(["SEQUENCE", "SEQUENCE", "PARALLEL"], ["SEQUENCE", "UNKNOWN", "PARALLEL"])
    assert res["predicted_columns"][-1] == "UNKNOWN"
    assert res["confusion_matrix"][LABELS.index("SEQUENCE")][-1] == 1
    assert res["per_class"]["SEQUENCE"]["recall"] == pytest.approx(0.5)
    assert res["accuracy"] == pytest.approx(2 / 3)
    assert all(sum(row) == m["support"] for row, m in zip(res["confusion_matrix"], res["per_class"].values()))


def test_stored_final_run_reproduces_published_matrix():
    samples = load_dataset(REPO / "benchmark_silver_2.jsonl")
    preds = predictions_from_report(REPO / "benchmark_results_silver_fewshot_final2.md", samples)
    res = compute([s["label"] for s in samples], preds)
    assert (res["correct"], res["n"]) == (274, 302)
    published = {  # paper Fig. 5, rows true, columns predicted
        ("CONDITION_DEF", "CONDITION_DEF"): 48, ("FALSE_BRANCH", "FALSE_BRANCH"): 48,
        ("FALSE_BRANCH", "TRUE_BRANCH"): 21, ("PARALLEL", "PARALLEL"): 46,
        ("SEQUENCE", "PARALLEL"): 4, ("SEQUENCE", "SEQUENCE"): 62,
        ("TRUE_BRANCH", "CONDITION_DEF"): 3, ("TRUE_BRANCH", "TRUE_BRANCH"): 70,
    }
    for i, t in enumerate(res["labels"]):
        for j, p in enumerate(res["predicted_columns"]):
            assert res["confusion_matrix"][i][j] == published.get((t, p), 0), (t, p)
