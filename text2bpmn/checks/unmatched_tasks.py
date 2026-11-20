"""The tasks the release matcher left unmatched in a case study, side by side,
and how close each unmatched generated task came to a reference task.

    python3 -m text2bpmn.checks.unmatched_tasks [--run runs/final-3/cases]
        [--cases healthcare goods_dispatch] [--reference CASE=PATH ...]
        [--name unmatched_tasks] [--out runs/checks/final-3/unmatched_tasks]

Diagnostic only: it reads a run's model.bpmn and comparison.json and changes
nothing. The matcher is text2bpmn.compare as it is -- read_bpmn, similarity,
match_tasks and DEFAULT_THRESHOLD are imported, not copied. For every case it

- matches the reference tasks to the generated ones with match_tasks, exactly
  as compare() did in the run (run_final.py, the line that calls
  `compare(read_bpmn(...reference.bpmn), ...)`, with the default threshold);
- lists the reference tasks and the generated tasks left unmatched;
- gives each unmatched generated task the best score it reached against any
  reference task under compare.similarity, that reference task (all of them on
  a tie), and whether it was already matched to another generated task;
- gives each unmatched task the partner the optimal assignment paired it with
  below the threshold (compare.py repeats linear_sum_assignment on the same
  scores here, and checks that it gives match_tasks' mapping back);
- checks that compare() on the same two files gives the task TP/FP/FN, the
  mapping and the unmatched lists saved in the run's comparison.json.

The reference defaults to text2bpmn/cases/<case>/reference.bpmn, the file
run_final.py reads. `--reference CASE=PATH` scores a case against another
reference (a replaced loan reference, say): the saved comparison.json was made
with the old one, so its counts are then compared and any difference reported,
not required to agree, and the record says whether the reference file is the
one the run scored against (run_final.py's path at the run's commit). Each
call writes <name>.json and <name>.md, so a later case can go beside these
with its own --name.
"""
import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from scipy.optimize import linear_sum_assignment

from text2bpmn import compare as matcher
from text2bpmn.checks.common import header, provenance, write
from text2bpmn.run_config import _version

RUN = "runs/final-3/cases"
CASES = ("healthcare", "goods_dispatch")
OUT = "runs/checks/final-3/unmatched_tasks"
COMPARE_PY = Path(matcher.__file__).resolve()
RUN_FINAL_PY = COMPARE_PY.parent / "run_final.py"
ROOT = COMPARE_PY.parent.parent


def default_reference(case):
    return f"text2bpmn/cases/{case}/reference.bpmn"  # as run_final.py reads it


def line_of(path, text):
    """`path:line` of the first line holding `text`, for the record."""
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if text in line:
            return f"{Path(path).relative_to(ROOT)}:{number}"
    return None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def blob_at(commit, path):
    """The bytes of `path` at `commit`, or None when git has no such file."""
    done = subprocess.run(("git", "show", f"{commit}:{path}"), capture_output=True)
    return done.stdout if done.returncode == 0 else None


def task_row(task):
    return {"id": task.id, "name": task.name}


def best_of(row, tasks):
    """The highest score in `row` and every task reaching it (to 1e-9, as the
    three views of compare.similarity can give one value in different ways)."""
    best = max(row) if row else 0.0
    return best, [tasks[k] for k, s in enumerate(row) if abs(s - best) < 1e-9]


def analyse(case, run, reference_path):
    run = Path(run)
    generated_path = run / case / "model.bpmn"
    saved = json.loads((run / case / "comparison.json").read_text(encoding="utf-8"))
    case_record = json.loads((run / case / "run_record.json").read_text(encoding="utf-8"))
    commit = case_record["code"]["commit"]

    reference_bytes = Path(reference_path).read_bytes()
    # the reference the run scored against: run_final.py's path at the run's commit
    at_run = blob_at(commit, default_reference(case))
    reference_info = {"path": str(reference_path), "sha256": sha256(reference_bytes),
                      "run_commit": commit, "run_reference": default_reference(case),
                      "run_reference_sha256": sha256(at_run) if at_run is not None else None,
                      "same_as_run_reference": at_run == reference_bytes if at_run is not None else None}

    reference, generated = matcher.read_bpmn(reference_path), matcher.read_bpmn(generated_path)
    ref, gen = reference.tasks, generated.tasks
    threshold = matcher.DEFAULT_THRESHOLD

    # the release matcher itself
    mapping = matcher.match_tasks(reference, generated)
    # the same scores and assignment as match_tasks (compare.py), kept so that
    # the below-threshold pairs and every best score can be reported
    scores = [[matcher.similarity(r.name, g.name) for g in gen] for r in ref]
    rows, columns = linear_sum_assignment([[-s for s in row] for row in scores])
    assigned = {(int(i), int(j)) for i, j in zip(rows, columns)}
    again = {ref[i].id: gen[j].id for i, j in assigned if scores[i][j] >= threshold}
    if again != mapping:
        raise RuntimeError(f"{case}: the repeated assignment does not give match_tasks' mapping")
    ref_index = {t.id: i for i, t in enumerate(ref)}
    gen_index = {t.id: j for j, t in enumerate(gen)}
    partner_of_ref = {i: j for i, j in assigned}
    partner_of_gen = {j: i for i, j in assigned}
    matched_gen = {g: r for r, g in mapping.items()}

    def matched_to(ref_task):
        g = mapping.get(ref_task.id)
        if g is None:
            return None
        return {**task_row(generated.nodes[g]), "score": scores[ref_index[ref_task.id]][gen_index[g]]}

    def ref_matched_to(gen_task):
        r = matched_gen.get(gen_task.id)
        if r is None:
            return None
        return {**task_row(reference.nodes[r]), "score": scores[ref_index[r]][gen_index[gen_task.id]]}

    unmatched_generated = []
    for j, g in enumerate(gen):
        if g.id in matched_gen:
            continue
        best, tops = best_of([scores[i][j] for i in range(len(ref))], ref)
        i = partner_of_gen.get(j)
        unmatched_generated.append({
            **task_row(g), "best_score": best,
            "best_reference": [{**task_row(r), "already_matched_to": matched_to(r)} for r in tops],
            "assigned_below_threshold": ({**task_row(ref[i]), "score": scores[i][j]} if i is not None else None)})

    unmatched_reference = []
    for i, r in enumerate(ref):
        if r.id in mapping:
            continue
        best, tops = best_of(scores[i], gen)
        j = partner_of_ref.get(i)
        unmatched_reference.append({
            **task_row(r), "best_score": best,
            "best_generated": [{**task_row(g), "already_matched_to": ref_matched_to(g)} for g in tops],
            "assigned_below_threshold": ({**task_row(gen[j]), "score": scores[i][j]} if j is not None else None)})

    # an unmatched pair that clears the threshold would be a match the
    # assignment gave away for a larger total; list any
    unmatched_ref_ids = {u["id"] for u in unmatched_reference}
    missed = [{"generated": u["name"], "reference": b["name"], "score": u["best_score"]}
              for u in unmatched_generated if u["best_score"] >= threshold
              for b in u["best_reference"] if b["id"] in unmatched_ref_ids]

    result = matcher.compare(reference, generated)
    counts = {k: result["tasks"][k] for k in ("tp", "fp", "fn")}
    saved_counts = {k: saved["tasks"][k] for k in ("tp", "fp", "fn")}
    mine = {"tp": len(mapping), "fp": len(unmatched_generated), "fn": len(unmatched_reference)}
    names = lambda items: Counter(items)
    agreement = {
        "counts_recomputed_by_compare": counts, "counts_from_these_sets": mine,
        "counts_saved": saved_counts,
        "counts_reproduce_saved": counts == saved_counts == mine,
        "mapping_reproduces_saved": names(map(tuple, result["mapping"])) == names(map(tuple, saved["mapping"])),
        "unmatched_reference_reproduces_saved":
            names(u["name"] for u in unmatched_reference) == names(saved["unmatched_reference"]),
        "unmatched_generated_reproduces_saved":
            names(u["name"] for u in unmatched_generated) == names(saved["unmatched_generated"]),
    }
    agreement["differences"] = {k: {"recomputed": counts[k], "saved": saved_counts[k]}
                                for k in counts if counts[k] != saved_counts[k]}

    config = case_record["config"]
    return {
        "case": case, "generated": str(generated_path), "reference": reference_info,
        "comparison_json": str(run / case / "comparison.json"),
        "run": {"commit": commit, "describe": case_record["code"]["describe"],
                "llm_model": config.get("llm_model"), "allow_no_llm": config.get("allow_no_llm"),
                "relation_mode": config.get("relation_mode"), "ner_model_path": config.get("ner_model_path")},
        "threshold": threshold, "reference_tasks": len(ref), "generated_tasks": len(gen),
        "matched": [{"reference": task_row(reference.nodes[r]), "generated": task_row(generated.nodes[g]),
                     "score": scores[ref_index[r]][gen_index[g]]} for r, g in mapping.items()],
        "unmatched_reference": unmatched_reference, "unmatched_generated": unmatched_generated,
        "unmatched_pairs_above_threshold": missed, "agreement": agreement,
        "score_matrix": {"reference": [t.id for t in ref], "generated": [t.id for t in gen], "scores": scores},
    }


def cell(text):
    return str(text).replace("|", "\\|")


def matched_note(entry):
    m = entry["already_matched_to"]
    return f"yes, to '{cell(m['name'])}' ({m['score']:.3f})" if m else "no"


def case_markdown(a):
    lines = [f"## {a['case']}", "",
             f"Generated `{a['generated']}` (run at {a['run']['describe']}, {a['run']['commit'][:7]}; "
             f"LLM {a['run']['llm_model']}, no-LLM {a['run']['allow_no_llm']}, relation mode "
             f"{a['run']['relation_mode']}, NER `{a['run']['ner_model_path']}`).",
             f"Reference `{a['reference']['path']}` (sha256 {a['reference']['sha256'][:12]}; the same file as "
             f"the one the run scored against, `{a['reference']['run_reference']}` at "
             f"{a['reference']['run_commit'][:7]}: {a['reference']['same_as_run_reference']}).",
             f"{a['reference_tasks']} reference tasks, {a['generated_tasks']} generated tasks, "
             f"{len(a['matched'])} matched at threshold {a['threshold']}.", ""]
    g = a["agreement"]
    lines += ["| task counts | TP | FP | FN |", "|---|---|---|---|",
              "| saved, `{}` | {tp} | {fp} | {fn} |".format(a["comparison_json"], **g["counts_saved"]),
              "| compare() now | {tp} | {fp} | {fn} |".format(**g["counts_recomputed_by_compare"]),
              "| the lists below | {tp} | {fp} | {fn} |".format(**g["counts_from_these_sets"]), "",
              f"Counts reproduce comparison.json: {g['counts_reproduce_saved']}; mapping: "
              f"{g['mapping_reproduces_saved']}; unmatched reference names: "
              f"{g['unmatched_reference_reproduces_saved']}; unmatched generated names: "
              f"{g['unmatched_generated_reproduces_saved']}."
              + (f" Differences: {g['differences']}." if g["differences"] else ""), ""]

    lines += ["### Unmatched, side by side", "",
              "The two lists are in model order; a row does not pair the two sides. Best score: the highest "
              "compare.similarity the generated task reaches against any reference task.", "",
              "| # | Reference task not matched | Generated task not matched | Best score | "
              "Best reference task | Already matched? |", "|---|---|---|---|---|---|"]
    refs, gens = a["unmatched_reference"], a["unmatched_generated"]
    for k in range(max(len(refs), len(gens))):
        left = cell(refs[k]["name"]) if k < len(refs) else ""
        if k < len(gens):
            u = gens[k]
            right = [cell(u["name"]), f"{u['best_score']:.3f}",
                     " / ".join(cell(b["name"]) for b in u["best_reference"]),
                     " / ".join(matched_note(b) for b in u["best_reference"])]
        else:
            right = ["", "", "", ""]
        lines.append(f"| {k + 1} | {left} | " + " | ".join(right) + " |")
    lines.append("")
    if a["unmatched_pairs_above_threshold"]:
        lines += ["Unmatched pairs at or above the threshold (the assignment gave them away):", ""]
        lines += [f"- {cell(m['generated'])} / {cell(m['reference'])}: {m['score']:.3f}"
                  for m in a["unmatched_pairs_above_threshold"]]
    else:
        lines.append("No unmatched generated task reaches the threshold against an unmatched reference task.")
    lines.append("")

    lines += ["### Unmatched reference tasks: nearest generated task", "",
              "| Reference task | Best score | Best generated task | Already matched? | "
              "Assigned below the threshold to |", "|---|---|---|---|---|"]
    for u in refs:
        partner = u["assigned_below_threshold"]
        lines.append(f"| {cell(u['name'])} | {u['best_score']:.3f} | "
                     + " / ".join(cell(b["name"]) for b in u["best_generated"]) + " | "
                     + " / ".join(matched_note(b) for b in u["best_generated"]) + " | "
                     + (f"{cell(partner['name'])} ({partner['score']:.3f})" if partner else "none") + " |")
    lines += ["", "### Unmatched generated tasks: the assignment's partner", "",
              "| Generated task | Assigned below the threshold to |", "|---|---|"]
    for u in gens:
        partner = u["assigned_below_threshold"]
        lines.append(f"| {cell(u['name'])} | "
                     + (f"{cell(partner['name'])} ({partner['score']:.3f})" if partner
                        else "none (more generated than reference tasks)") + " |")
    lines += ["", "### Matched pairs", "", "| Reference task | Generated task | Score |", "|---|---|---|"]
    lines += [f"| {cell(m['reference']['name'])} | {cell(m['generated']['name'])} | {m['score']:.3f} |"
              for m in sorted(a["matched"], key=lambda m: m["score"])]
    return lines + [""]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default=RUN, help=f"the run's cases folder (default {RUN})")
    ap.add_argument("--cases", nargs="+", default=list(CASES))
    ap.add_argument("--reference", action="append", default=[], metavar="CASE=PATH",
                    help="score CASE against PATH instead of text2bpmn/cases/CASE/reference.bpmn")
    ap.add_argument("--name", default="unmatched_tasks", help="basename of the .json and .md written")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    references = dict(item.split("=", 1) for item in args.reference)
    unknown = set(references) - set(args.cases)
    if unknown:
        raise SystemExit(f"--reference for cases not in --cases: {sorted(unknown)}")

    sources = {"threshold": line_of(COMPARE_PY, "DEFAULT_THRESHOLD = "),
               "threshold_test": line_of(COMPARE_PY, "if scores[i][j] >= threshold"),
               "similarity": line_of(COMPARE_PY, "def similarity("),
               "match_tasks": line_of(COMPARE_PY, "def match_tasks("),
               "assignment": line_of(COMPARE_PY, "linear_sum_assignment([[-s for s in row]"),
               "run_final_compare_call": line_of(RUN_FINAL_PY, "compare(read_bpmn(")}
    # the assignment is scipy's, so its version is recorded beside the run's
    run_freeze = Path(args.run).parent / "pip_freeze.txt"
    pinned = {line.split("==")[0]: line.split("==")[1] for line in
              (run_freeze.read_text(encoding="utf-8").splitlines() if run_freeze.exists() else [])
              if line.split("==")[0] in ("scipy", "numpy") and "==" in line}
    record = provenance(run=args.run, cases=args.cases, references=references, sources=sources,
                        assignment_packages={"now": {p: _version(p) for p in ("scipy", "numpy")},
                                             "in_the_run": pinned, "run_freeze": str(run_freeze)})
    analyses = [analyse(case, args.run, references.get(case, default_reference(case))) for case in args.cases]

    lines = header("Unmatched tasks in the case studies", record)
    lines += [f"Run `{args.run}`. Matcher: text2bpmn.compare as it is. Tasks are matched one-to-one by "
              f"an optimal assignment (scipy linear_sum_assignment, {sources['assignment']}) on "
              f"compare.similarity ({sources['similarity']}): the largest of the character ratio, the "
              "ratio with words sorted, and the overlap of five-character word stems, on lower-cased "
              "labels without punctuation or articles. A pair counts as matched when its score is at least "
              f"the threshold DEFAULT_THRESHOLD = {matcher.DEFAULT_THRESHOLD} ({sources['threshold']}, "
              f"tested at {sources['threshold_test']}); the run called compare() with the default "
              f"({sources['run_final_compare_call']}).",
              f"scipy and numpy here: {record['assignment_packages']['now']}; in the run "
              f"(`{record['assignment_packages']['run_freeze']}`): {record['assignment_packages']['in_the_run']}.",
              ""]
    lines += ["| case | reference tasks | generated tasks | TP | FP | FN | reproduces comparison.json |",
              "|---|---|---|---|---|---|---|"]
    for a in analyses:
        g = a["agreement"]
        lines.append("| {} | {} | {} | {tp} | {fp} | {fn} | {} |".format(
            a["case"], a["reference_tasks"], a["generated_tasks"], g["counts_reproduce_saved"]
            and g["mapping_reproduces_saved"] and g["unmatched_reference_reproduces_saved"]
            and g["unmatched_generated_reproduces_saved"], **g["counts_from_these_sets"]))
    lines.append("")
    for a in analyses:
        lines += case_markdown(a)
    result = {"provenance": record, "threshold": matcher.DEFAULT_THRESHOLD,
              "cases": {a["case"]: a for a in analyses}}
    print("wrote", write(args.out, args.name, result, "\n".join(lines)))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
