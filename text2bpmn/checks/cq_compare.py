"""Populate the three reference models and compare their competency-question
answers with the generated models', as sets, question by question.

    python3 -m text2bpmn.checks.cq_compare runs/pilot runs/pilot_scripted
    python3 -m text2bpmn.checks.cq_compare runs/final-3/cases runs/final-3/cases_no_llm \
        runs/gliner-3/cases_gliner runs/gliner-3/cases_gliner_no_llm --layout release \
        --out runs/checks/final-3/cq_compare --references runs/checks/final-3/cq_compare/references

Each reference (text2bpmn/cases/<case>/reference.bpmn) is read by
reference_reader.py and populated with ontology.populate(..., validate=False)
into runs/checks/references/<case>/ontology.owl. The eight queries in
text2bpmn/checks/cq/ then run on it and on each generated case graph:
<pilot>/case-<case>/ontology.owl for a pilot (--layout pilot, the default), or
<experiment>/<case>/ontology.owl for the release runs (--layout release:
runs/final-3/cases, runs/gliner-3/cases_gliner, ...). BBO is read from
--ontology and must have the SHA-256 checks/fetch_bbo.py pins; the command
line is kept in the report.

Generated and reference tasks are worded differently, so a generated task
label is replaced by the reference task it matches and is kept as
"(unmatched) <label>" when it matches none. The matching is the structural
comparison's own, text2bpmn.compare.match_tasks: labels are normalised
(lower case, accents and punctuation dropped, articles removed) and scored by
compare.similarity, the largest of three ratios -- difflib's
SequenceMatcher on the two labels, the same on their words sorted, and the
Dice overlap of their words cut to five letters -- and the tasks are paired
one to one by optimal assignment (scipy's linear_sum_assignment) where the
score is at least compare.DEFAULT_THRESHOLD, 0.5. Lanes are compared without
case or a leading article. Each answer becomes keys:

    CQ1 (lane, task)            CQ5 (from task, to task)
    CQ2 {task, task}            CQ6 {task, task}
    CQ3 {task, task}            CQ7 task
    CQ4 (task, successor type, successor task)
    CQ8 the four counts, compared number by number

CQ2 and CQ6 are scored as unordered pairs of alternative tasks, so that the
comparison does not depend on which outcome a model calls yes: the loan text
says "if the applicant is not eligible", the reference asks "eligible?", and
the same rejection is a TRUE branch in one and a FALSE branch in the other.
For CQ2 a pair is the next tasks of two different outgoing flows of one
decision; for CQ6, two tasks each reached only through a different outgoing
flow of one decision (cq/pairs/alternatives.rq).

and per question the report gives |reference|, |generated|, |both|,
precision (both / generated) and recall (both / reference). CQ1 and CQ5 name
participants; against a reference without any (the loan's textbook reference
has no lanes) they are reported as n/a.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

import rdflib

from text2bpmn.checks.common import header, provenance, write
from text2bpmn.checks.competency_questions import CQ, load_graph, queries, run
from text2bpmn.checks.fetch_bbo import FILES as BBO_FILES
from text2bpmn.checks.reference_reader import read_reference
from text2bpmn.compare import compare, normalise, read_bpmn
from text2bpmn.ontology import populate

CASES = ("loan", "goods_dispatch", "healthcare")
ONTOLOGY = "BPMNbasedOntologyV1_2.owl"
BBO_SHA256 = BBO_FILES[ONTOLOGY][1]
LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+")
# where a run keeps one case's model.bpmn and ontology.owl
LAYOUTS = {"pilot": "case-{case}", "release": "{case}"}


def case_folder(pilot, case, layout="pilot"):
    return Path(pilot) / LAYOUTS[layout].format(case=case)


def lane(text):
    return LEADING_ARTICLE.sub("", re.sub(r"\s+", " ", (text or "").lower()).strip())


ALTERNATIVES = {"question": "tasks only one outcome of a decision reaches",
                "text": (CQ / "pairs" / "alternatives.rq").read_text(encoding="utf-8")}


def alternative_pairs(rows, task, column):
    """Unordered pairs of tasks on different outgoing flows of one decision."""
    by_flow = {}
    for r in rows:
        by_flow.setdefault(r["gateway"], {}).setdefault(r["flow_id"], set()).add(task(r[column]))
    pairs = set()
    for flows in by_flow.values():
        groups = list(flows.values())
        for i, a in enumerate(groups):
            for b in groups[i + 1:]:
                pairs |= {frozenset((x, y)) for x in a for y in b if x != y}
    return pairs


def keys(name, rows, task):
    """Comparable keys for one question's answer rows (CQ6: the alternatives query's)."""
    if name == "cq1":
        return {(lane(r["participant"]), task(r["task"])) for r in rows}
    if name == "cq2":
        return alternative_pairs(rows, task, "next_task")
    if name == "cq6":
        return alternative_pairs(rows, task, "task")
    if name == "cq3":
        return {frozenset((task(r["task_a"]), task(r["task_b"]))) for r in rows}
    if name == "cq4":
        return {(task(r["task"]), r["successor_type"],
                 task(r["successor"]) if r["successor_type"] == "Task" else "") for r in rows}
    if name == "cq5":
        return {(task(r["from_task"]), task(r["to_task"])) for r in rows}
    if name == "cq7":
        return {task(r["task"]) for r in rows}
    raise KeyError(name)


PARTICIPANT_QUESTIONS = ("cq1", "cq5")   # their answers name lanes (participants)


def compare_question(name, reference, generated, reference_participants):
    """compare_sets, except that a question about participants does not apply
    to a reference without participants (the loan's textbook reference has no
    lanes): it is reported as n/a, not as precision 0 and recall undefined."""
    if name in PARTICIPANT_QUESTIONS and not reference_participants:
        return {"not_applicable": "no participants in the reference", "reference": 0,
                "generated": len(generated), "both": 0, "precision": None, "recall": None,
                "reference_only": [], "generated_only": shown(generated)[:5]}
    return compare_sets(reference, generated)


def show(key):
    """A key as text, the same on every run: an unordered pair as {a, b}, a tuple as (a, b, ...)."""
    if isinstance(key, frozenset):
        return "{" + ", ".join(sorted(key)) + "}"
    if isinstance(key, tuple):
        return "(" + ", ".join(part for part in key if part) + ")"
    return str(key)


def shown(keys_):
    return sorted(map(show, keys_))


def compare_sets(reference, generated):
    both = reference & generated
    return {"reference": len(reference), "generated": len(generated), "both": len(both),
            "precision": round(len(both) / len(generated), 3) if generated else None,
            "recall": round(len(both) / len(reference), 3) if reference else None,
            "reference_only": shown(reference - generated)[:5],
            "generated_only": shown(generated - reference)[:5]}


def fmt(c):
    if c.get("not_applicable"):
        return "n/a"
    if c.get("counts"):
        return " ".join(f"{k[:4]} {v['reference']}/{v['generated']}" for k, v in c["counts"].items())
    p = "-" if c["precision"] is None else f"{c['precision']:.2f}"
    r = "-" if c["recall"] is None else f"{c['recall']:.2f}"
    return f"{c['both']}/{c['reference']}/{c['generated']} (P {p}, R {r})"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pilots", nargs="+")
    ap.add_argument("--out", default="runs/checks/cq_compare")
    ap.add_argument("--references", default="runs/checks/references")
    ap.add_argument("--layout", choices=tuple(LAYOUTS), default="pilot",
                    help="pilot: <pilot>/case-<case>/; release: <experiment>/<case>/ (runs/final-3/cases)")
    ap.add_argument("--ontology", default=ONTOLOGY,
                    help="BBO, as text2bpmn/checks/fetch_bbo.py fetches it (read only)")
    args = ap.parse_args()
    digest = hashlib.sha256(Path(args.ontology).read_bytes()).hexdigest()
    if digest != BBO_SHA256:
        raise SystemExit(f"{args.ontology}: SHA-256 {digest}, not the pinned {BBO_SHA256}")
    qs = queries()
    bbo = rdflib.Graph().parse(args.ontology)
    command = ["python3", "-m", "text2bpmn.checks.cq_compare", *sys.argv[1:]]
    record = provenance(pilots=args.pilots, layout=args.layout, ontology=args.ontology,
                        ontology_sha256=digest, command=command,
                        references={case: f"text2bpmn/cases/{case}/reference.bpmn" for case in CASES})
    result = {"provenance": record, "cases": {}}
    lines = header("Competency answers: generated against reference, as sets", record)
    lines += [f"Command: `{' '.join(record['command'])}`", "",
              "Each cell: both / reference / generated, with precision and recall; CQ2 and CQ6 count "
              "unordered pairs of alternative tasks; CQ8 gives reference / generated for tasks, decisions, "
              "parallel blocks and participants; n/a: a question about participants (CQ1, CQ5) on a "
              "reference that has none. Tasks are matched by text2bpmn.compare.match_tasks "
              "(compare.similarity, threshold 0.5, one-to-one). References: "
              + ", ".join(f"`{p}`" for p in record["references"].values()) + ".", ""]
    for case in CASES:
        reference_bpmn = Path(f"text2bpmn/cases/{case}/reference.bpmn")
        ref_owl = Path(args.references) / case / "ontology.owl"
        summary = populate(read_reference(reference_bpmn, case), args.ontology, ref_owl, validate=False)
        ref_graph = load_graph(ref_owl, bbo)
        ref_answers = {n: run(ref_graph, n, q) for n, q in qs.items()}
        ref_alternatives = run(ref_graph, "cq6", ALTERNATIVES)["rows"]
        ref_keys = {n: (keys(n, ref_alternatives, normalise) if n == "cq6" else keys(n, ref_answers[n]["rows"], normalise))
                    for n in qs if n != "cq8"}
        result["cases"][case] = {"reference": {"populated": summary, "answers": ref_answers,
                                               "alternatives": ref_alternatives,
                                               "keys": {n: shown(k) for n, k in ref_keys.items()}},
                                 "generated": {}}
        lines += [f"## {case}", "", "| source | " + " | ".join(qs) + " |", "|---" * (len(qs) + 1) + "|"]
        for pilot in args.pilots:
            folder = case_folder(pilot, case, args.layout)
            matched = compare(read_bpmn(reference_bpmn), read_bpmn(folder / "model.bpmn"))["mapping"]
            to_reference = {normalise(g): normalise(r) for r, g in matched}
            gen_task = lambda label: to_reference.get(normalise(label), f"(unmatched) {normalise(label)}")
            gen_graph = load_graph(folder / "ontology.owl", bbo)
            gen_answers = {n: run(gen_graph, n, q) for n, q in qs.items()}
            gen_alternatives = run(gen_graph, "cq6", ALTERNATIVES)["rows"]
            ref_participants = int(ref_answers["cq8"]["rows"][0]["participants"])
            per = {}
            for n in qs:
                if n == "cq8":
                    ref_row, gen_row = ref_answers[n]["rows"][0], gen_answers[n]["rows"][0]
                    per[n] = {"counts": {k: {"reference": int(ref_row[k]), "generated": int(gen_row[k])}
                                         for k in ref_row}}
                elif n == "cq6":
                    per[n] = compare_sets(keys(n, ref_alternatives, normalise),
                                          keys(n, gen_alternatives, gen_task))
                else:
                    per[n] = compare_question(n, keys(n, ref_answers[n]["rows"], normalise),
                                              keys(n, gen_answers[n]["rows"], gen_task), ref_participants)
            gen_keys = {n: shown(keys(n, gen_alternatives, gen_task) if n == "cq6"
                                 else keys(n, gen_answers[n]["rows"], gen_task)) for n in qs if n != "cq8"}
            result["cases"][case]["generated"][pilot] = {"task_matches": matched, "answers": gen_answers,
                                                         "alternatives": gen_alternatives, "keys": gen_keys,
                                                         "comparison": per}
            lines.append(f"| {pilot} | " + " | ".join(fmt(per[n]) for n in qs) + " |")
        lines.append("")
    print("wrote", write(args.out, "cq_compare", result, "\n".join(lines)))
    answers_md = Path(args.out) / "cq_answers.md"
    answers_md.write_text(answers_report(result, qs, record), encoding="utf-8")
    print("wrote", answers_md)
    print("\n".join(lines[3:]))


def _cpu():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown CPU"


def answers_report(result, qs, record):
    """The queries verbatim, each graph's answer as the keys it is scored on,
    the score cells and the query times, in one Markdown file."""
    lines = header("Competency questions: queries, answers, scores and run times", record)
    lines += [f"Command: `{' '.join(record['command'])}`. Scores and keys as in `cq_compare.md`: a generated task is "
              "named by the reference task it matches, or `(unmatched) <label>`; CQ2 and CQ6 are unordered pairs of "
              "alternative tasks (CQ6 from the alternatives query below); CQ8 gives the four counts.", "",
              "## The queries (text2bpmn/checks/cq/, verbatim)", ""]
    for n, q in qs.items():
        lines += [f"### {n}", "", "```sparql", q["text"].rstrip(), "```", ""]
    lines += ["### alternatives (scores CQ6; text2bpmn/checks/cq_compare.py ALTERNATIVES)", "", "```sparql",
              ALTERNATIVES["text"].rstrip(), "```", ""]
    names = [n for n in qs]
    lines += ["## Query run times (seconds; rdflib " + str(record["packages"].get("rdflib")) + f", {_cpu()})", "",
              "| case | graph | " + " | ".join(names) + " | total |", "|---" * (len(names) + 3) + "|"]
    times = {n: [] for n in names}
    for case, entry in result["cases"].items():
        graphs = [("reference", entry["reference"]["answers"])] + [(p, g["answers"]) for p, g in entry["generated"].items()]
        for label, answers in graphs:
            row = [answers[n]["seconds"] for n in names]
            for n, t in zip(names, row):
                times[n].append(t)
            lines.append(f"| {case} | {label} | " + " | ".join(f"{t:.3f}" for t in row) + f" | {sum(row):.3f} |")
    lines += ["", "| question | graphs | min | median | max |", "|---|---|---|---|---|"]
    for n in names:
        ts = sorted(times[n])
        lines.append(f"| {n} | {len(ts)} | {ts[0]:.3f} | {ts[len(ts) // 2]:.3f} | {ts[-1]:.3f} |")
    lines.append("")
    for case, entry in result["cases"].items():
        ref = entry["reference"]
        lines += [f"## {case}", "", f"Reference: `text2bpmn/cases/{case}/reference.bpmn`.", ""]
        for n in names:
            lines += [f"### {n} {qs[n]['question'][4:]}", ""]
            if n == "cq8":
                row = ref["answers"][n]["rows"][0]
                lines.append("- reference: " + ", ".join(f"{k} {v}" for k, v in row.items()))
                for p, g in entry["generated"].items():
                    gr = g["answers"][n]["rows"][0]
                    lines.append(f"- {p}: " + ", ".join(f"{k} {v}" for k, v in gr.items()))
            else:
                rk = ref["keys"][n]
                why = ref["answers"][n].get("empty_because", "") if n != "cq6" else ""
                lines.append(f"- reference ({len(rk)}): " + ("; ".join(rk) if rk else f"none{' (' + why + ')' if why else ''}"))
                for p, g in entry["generated"].items():
                    gk = g["keys"][n]
                    lines.append(f"- {p}: **{fmt(g['comparison'][n])}**; answer ({len(gk)}): "
                                 + ("; ".join(gk) if gk else "none"))
            lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
