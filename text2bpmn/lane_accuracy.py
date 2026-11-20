"""Lane assignment scored against PET's actor-performer relations.

    python3 -m text2bpmn.lane_accuracy runs/final/coref_ablation [--out DIR]

For the coreference ablation (text2bpmn/run_final.py, run 6): in each arm's
document folders, every activity PET gives a performer is found among the
pipeline's tasks and its lane compared with that performer.

- **Alignment.** The pipeline recognises spans in the text it processed, which
  with FastCoref has pronouns replaced. Its spans are mapped back to the
  original text by aligning the two character by character (difflib); a
  replaced stretch maps onto the original stretch it replaced.
- **Matching.** A gold activity is the pipeline task whose Activity span,
  mapped back, overlaps it most. A gold activity no task overlaps is counted
  as not recognised, not as wrong.
- **The expected lane** is the gold performer's text. Where the performer is a
  pronoun -- PET annotates "he", not its antecedent, and has no coreference
  layer -- it is the nearest earlier gold Actor mention that is not one;
  these activities are reported separately, being where coreference should
  matter.
- **A match** is the same name after lower-casing and dropping a leading
  article, a possessive and punctuation, or one name's words all within the
  other's ("customer service" in "customer service department").

Per arm: activities scored, the share in their performer's lane, the share in
the "Main Process" lane -- the lane an element gets when no actor is found
before it -- and the same over every task of the models.

--exclude-recipients scores again without the activities that PET also gives
an actor recipient, as a check that recipients do not distort the score (the
pipeline never takes a recipient's lane: finder3._is_recipient). It prints the
table and writes nothing, so the run's lane_scores stay as they were. Without
--out the scores are written into the folder scored, over the run's own
lane_scores (as run_final.py and run_gliner_arm.py write them); --out writes
them elsewhere, leaving a committed run untouched.
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

from text2bpmn.pet_rules_eval import PET_DEFAULT, load_documents

M = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
PRONOUNS = {"he", "him", "she", "her", "it", "they", "them", "his", "hers", "its", "their", "theirs",
            "who", "which", "this", "that", "these", "those", "we", "us", "our", "i", "me", "you", "your"}
MAIN_PROCESS = "main process"


def normalise(name):
    name = re.sub(r"'s\b|’s\b", "", (name or "").lower())
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"^\s*(the|a|an)\s+", "", re.sub(r"\s+", " ", name).strip())
    return name.strip()


def same_actor(a, b):
    a, b = normalise(a), normalise(b)
    if not a or not b:
        return False
    return a == b or set(a.split()) <= set(b.split()) or set(b.split()) <= set(a.split())


def to_original(original, processed):
    """For each character of `processed`, its position in `original`."""
    position = [0] * (len(processed) + 1)
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, original, processed, autojunk=False).get_opcodes():
        for j in range(j1, j2):
            position[j] = i1 + (j - j1) if tag == "equal" else i1
    position[len(processed)] = len(original)
    return position


def lanes_of(model):
    process = ET.parse(model).getroot().find(M + "process")
    return {ref.text: lane.get("name") for lane in process.iter(M + "lane")
            for ref in lane.findall(M + "flowNodeRef")}


def expected_performers(document, exclude_recipients=False):
    """{(start, end) of a gold activity: (performer text, via a pronoun)}; with
    exclude_recipients, none of the activities PET also gives an actor recipient."""
    actors = sorted((s for s in document["spans"] if s["entity_group"] == "Actor"), key=lambda s: s["start"])
    with_recipient = {(s["start"], s["end"]) for kind, s, _ in document["relations"]
                      if kind == "actor recipient"} if exclude_recipients else set()
    out = {}
    for kind, source, target in document["relations"]:
        if kind != "actor performer" or source["entity_group"] != "Activity":
            continue
        if (source["start"], source["end"]) in with_recipient:
            continue
        name, pronoun = target["word"], normalise(target["word"]) in PRONOUNS
        if pronoun:
            earlier = [a for a in actors if a["start"] < target["start"] and normalise(a["word"]) not in PRONOUNS]
            name = earlier[-1]["word"] if earlier else ""
        out[(source["start"], source["end"])] = (name, pronoun)
    return out


def score_document(folder, document, exclude_recipients=False):
    extraction = json.loads((folder / "extraction.json").read_text(encoding="utf-8"))
    log = (folder / "log.txt").read_text(encoding="utf-8")
    # the text the recogniser read: its own, or the one injected spans refer to
    marker = next(m for m in ("(Debug) Coref Resolved: ", "(Debug) Injected text: ") if m in log)
    processed = log.split(marker, 1)[1].split("\n", 1)[0]
    position = to_original(document["text"], processed)
    lanes = lanes_of(folder / "model.bpmn")
    tasks = [(position[e["start"]], position[e["end"]], e["id"]) for e in extraction["entities_used"]
             if e["label"] == "Activity" and e.get("start") is not None and e.get("id") in lanes]
    rows = []
    for (start, end), (expected, pronoun) in expected_performers(document, exclude_recipients).items():
        overlaps = [(min(end, e) - max(start, s), task) for s, e, task in tasks if min(end, e) > max(start, s)]
        if not overlaps:
            rows.append({"activity": document["text"][start:end], "recognised": False, "pronoun": pronoun})
            continue
        lane = lanes[max(overlaps)[1]]
        rows.append({"activity": document["text"][start:end], "recognised": True, "pronoun": pronoun,
                     "expected": expected, "lane": lane, "correct": same_actor(lane, expected),
                     "main_process": normalise(lane) == MAIN_PROCESS})
    all_lanes = [lanes[t] for _, _, t in tasks]
    return rows, all_lanes


def share(n, d):
    return round(n / d, 4) if d else None


def score_arm(arm_folder, documents, exclude_recipients=False):
    rows, all_lanes, missing = [], [], []
    for name, document in documents.items():
        folder = arm_folder / name
        if not (folder / "extraction.json").exists():
            continue
        if not (folder / "log.txt").exists():
            missing.append(name)
            continue
        r, lanes = score_document(folder, document, exclude_recipients)
        rows += [{**x, "document": name} for x in r]
        all_lanes += lanes
    scored = [r for r in rows if r["recognised"]]
    via_pronoun = [r for r in scored if r["pronoun"]]
    return {"activities_with_a_gold_performer": len(rows), "recognised": len(scored),
            "in_performer_lane": share(sum(r["correct"] for r in scored), len(scored)),
            "in_main_process_lane": share(sum(r["main_process"] for r in scored), len(scored)),
            "performer_is_a_pronoun": len(via_pronoun),
            "in_performer_lane_when_pronoun": share(sum(r["correct"] for r in via_pronoun), len(via_pronoun)),
            "tasks": len(all_lanes),
            "tasks_in_main_process_lane": share(sum(normalise(l) == MAIN_PROCESS for l in all_lanes),
                                                len(all_lanes)),
            "documents_without_log": missing, "rows": rows}


def score(folder, data=PET_DEFAULT, exclude_recipients=False, out=None):
    """Scores each arm of `folder`; writes lane_scores.{json,md} into `out`, by
    default `folder` itself (as the runs do), unless exclude_recipients."""
    documents = {d["name"]: d for d in load_documents(data)}
    folder = Path(folder)
    result = {arm: score_arm(folder / arm, documents, exclude_recipients) for arm in ("with_coref", "without_coref")
              if (folder / arm).exists()}
    lines = ["| arm | activities with a gold performer | recognised | in the performer's lane | "
             "in Main Process | performer a pronoun | in the performer's lane, pronoun | "
             "all tasks in Main Process |", "|---|---|---|---|---|---|---|---|"]
    pct = lambda v: "-" if v is None else f"{v:.1%}"
    for arm, r in result.items():
        lines.append(f"| {arm} | {r['activities_with_a_gold_performer']} | {r['recognised']} | "
                     f"{pct(r['in_performer_lane'])} | {pct(r['in_main_process_lane'])} | "
                     f"{r['performer_is_a_pronoun']} | {pct(r['in_performer_lane_when_pronoun'])} | "
                     f"{pct(r['tasks_in_main_process_lane'])} |")
    if exclude_recipients:  # a check, not the run's score: written nowhere
        return result, "\n".join(lines)
    out = Path(out) if out else folder
    out.mkdir(parents=True, exist_ok=True)
    (out / "lane_scores.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "lane_scores.md").write_text("# Lane assignment against PET's actor-performer relations\n\n"
                                           + "\n".join(lines) + "\n", encoding="utf-8")
    return result, "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", help="the coreference ablation's folder, with with_coref/ and without_coref/")
    ap.add_argument("--data", default=PET_DEFAULT)
    ap.add_argument("--exclude-recipients", action="store_true",
                    help="leave out activities that also have an actor recipient; print, write nothing")
    ap.add_argument("--out", help="write lane_scores.{json,md} here instead of into the folder scored")
    args = ap.parse_args()
    print(score(args.folder, args.data, args.exclude_recipients, args.out)[1])


if __name__ == "__main__":
    main()
