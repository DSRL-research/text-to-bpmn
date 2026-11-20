"""Pronoun performers in the 7 PET documents the recognisers never saw, with and without FastCoref.

    python3 -m text2bpmn.checks.unseen_pronoun_lanes
        # -> runs/checks/final-3/open_analyses/unseen_pronoun_lanes.{md,json}

The lane score on the 7 unseen documents is
36/46 for BERT with FastCoref: of the activities PET gives a performer, the 46
the pipeline recognised, 36 in their performer's lane. This check first
reproduces that figure, then counts how many of those activities have a pronoun
performer and how many of these reach the right lane in each arm of the
coreference ablation (runs/final-3/coref_ablation, with_coref / without_coref).

- **The unseen documents** are those of pet_test.json, which the clean split
  (text2bpmn/clean_split.py) keeps out of training (train_315.json) and
  development (dev_split.json); both sets of names are read to check this.
- **Scoring** is text2bpmn/lane_accuracy.py's, unchanged: score_document on
  each arm's saved document folder. It reads only saved files (extraction.json,
  log.txt, model.bpmn) and PET's gold annotation; nothing is run. Its rows are
  also checked against the run's own lane_scores.json.
- **A pronoun performer** is lane_accuracy's: the gold Actor Performer's text,
  lower-cased without a leading article, is in lane_accuracy.PRONOUNS ("he",
  "she", "it", "they", "who", "which", "we", "i", ...). The expected lane is
  then the nearest earlier gold Actor that is not a pronoun.
- Each gold activity's row is the same in both arms (lane_accuracy lists the
  gold activities in the same order), so the arms are compared activity by
  activity; an activity counts for an arm only if that arm recognised it.
"""
import json
from pathlib import Path

from text2bpmn import lane_accuracy as la
from text2bpmn.pet_rules_eval import PET_DEFAULT, load_documents

OUT = Path("runs/checks/final-3/open_analyses/unseen_pronoun_lanes")
ABLATION = Path("runs/final-3/coref_ablation")
ARMS = ("with_coref", "without_coref")


def unseen_documents():
    names = lambda path: {r["document name"] for r in json.loads(Path(path).read_text(encoding="utf-8"))}  # noqa
    test, train, dev = names("pet_test.json"), names("text2bpmn/baselines/train_315.json"), \
        names("text2bpmn/baselines/dev_split.json")
    assert not test & (train | dev), "the test documents overlap training or development"
    return sorted(test), len(train | dev)


def rows_of(arm, documents):
    """{document: [row per gold activity with a performer]} by lane_accuracy.score_document."""
    out = {}
    for name, document in documents.items():
        rows, _ = la.score_document(ABLATION / arm / name, document)
        keys = list(la.expected_performers(document))
        out[name] = [{**r, "span": list(k), "document": name} for r, k in zip(rows, keys)]
    return out


def analyse():
    unseen, n_seen = unseen_documents()
    documents = {d["name"]: d for d in load_documents(PET_DEFAULT) if d["name"] in unseen}
    assert sorted(documents) == unseen
    saved = json.loads((ABLATION / "lane_scores.json").read_text(encoding="utf-8"))
    rows = {arm: rows_of(arm, documents) for arm in ARMS}
    for arm in ARMS:  # rescored rows equal the run's own lane_scores.json rows
        mine = [{k: v for k, v in r.items() if k != "span"} for d in unseen for r in rows[arm][d]]
        theirs = [r for r in saved[arm]["rows"] if r["document"] in unseen]
        theirs = sorted(theirs, key=lambda r: unseen.index(r["document"]))
        assert mine == theirs, arm
    result = {"unseen_documents": unseen, "documents_seen_in_training_or_development": n_seen, "arms": {}}
    for arm in ARMS:
        flat = [r for d in unseen for r in rows[arm][d]]
        recognised = [r for r in flat if r["recognised"]]
        pronoun = [r for r in recognised if r["pronoun"]]
        result["arms"][arm] = {
            "activities_with_a_gold_performer": len(flat), "recognised": len(recognised),
            "in_performer_lane": sum(r["correct"] for r in recognised),
            "recognised_with_a_pronoun_performer": len(pronoun),
            "pronoun_in_performer_lane": sum(r["correct"] for r in pronoun),
            "gold_activities_with_a_pronoun_performer": sum(r["pronoun"] for r in flat)}
    # activity by activity: the pronoun-performer activities of the 46 (with FastCoref)
    paired = []
    for d in unseen:
        for w, wo in zip(rows["with_coref"][d], rows["without_coref"][d]):
            assert w["span"] == wo["span"] and w["pronoun"] == wo["pronoun"]
            if w["pronoun"] and (w["recognised"] or wo["recognised"]):
                text = documents[d]["text"]
                performer = next(t["word"] for kind, s, t in documents[d]["relations"]
                                 if kind == "actor performer" and [s["start"], s["end"]] == w["span"])
                paired.append({"document": d, "activity": w["activity"], "pronoun": performer,
                               "expected lane": w.get("expected") or wo.get("expected"),
                               "with_coref": {k: w.get(k) for k in ("recognised", "lane", "correct")},
                               "without_coref": {k: wo.get(k) for k in ("recognised", "lane", "correct")},
                               "context": text[max(0, w["span"][0] - 80):w["span"][1] + 20]})
    both = [p for p in paired if p["with_coref"]["recognised"] and p["without_coref"]["recognised"]]
    result["pronoun_activities"] = paired
    result["recognised_in_both_arms"] = {"n": len(both),
                                         "right_with": sum(bool(p["with_coref"]["correct"]) for p in both),
                                         "right_without": sum(bool(p["without_coref"]["correct"]) for p in both)}
    return result


def markdown(r):
    a = r["arms"]
    lines = ["# Pronoun performers on the 7 unseen PET documents, with and without FastCoref", "",
             "Generated by `text2bpmn/checks/unseen_pronoun_lanes.py` from `runs/final-3/coref_ablation` "
             "(lane_accuracy's scoring, rows checked against the run's `lane_scores.json`).", "",
             f"Unseen documents ({len(r['unseen_documents'])}): {', '.join(r['unseen_documents'])}; "
             f"training and development used {r['documents_seen_in_training_or_development']} others.", "",
             "| arm | gold activities with a performer | recognised | in performer's lane | "
             "recognised, pronoun performer | of those in the right lane |", "|---|---|---|---|---|---|"]
    for arm, x in a.items():
        lines.append(f"| {arm} | {x['activities_with_a_gold_performer']} | {x['recognised']} | "
                     f"{x['in_performer_lane']}/{x['recognised']} | {x['recognised_with_a_pronoun_performer']} | "
                     f"{x['pronoun_in_performer_lane']}/{x['recognised_with_a_pronoun_performer']} |")
    b = r["recognised_in_both_arms"]
    lines += ["", f"Pronoun-performer activities recognised in both arms: {b['n']}; right lane with FastCoref "
              f"{b['right_with']}, without {b['right_without']}.", "",
              "| document | activity | pronoun | expected lane | with: lane (right?) | without: lane (right?) |",
              "|---|---|---|---|---|---|"]
    cell = lambda x: (f"{x['lane']} ({'yes' if x['correct'] else 'no'})"  # noqa: E731
                      if x["recognised"] else "not recognised")
    for p in r["pronoun_activities"]:
        lines.append(f"| {p['document']} | {p['activity']} | {p['pronoun']} | {p['expected lane']} | "
                     f"{cell(p['with_coref'])} | {cell(p['without_coref'])} |")
    return "\n".join(lines) + "\n"


def main():
    result = analyse()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    text = markdown(result)
    OUT.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
