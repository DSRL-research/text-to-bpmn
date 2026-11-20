"""Loan competency answers against the textbook reference (decision D12),
beside the authored reference, for the four loan configurations of the
release runs.

    python3 -m text2bpmn.checks.loan_cq [--ontology BPMNbasedOntologyV1_2.owl] \
        [--out runs/checks/final-3/loan_reference/cq]

The same steps as text2bpmn/checks/cq_compare.py, for the loan case only,
with its functions: each reference is read by reference_reader.py, populated
with ontology.populate(..., validate=False) into <out>/references/<name>/,
and the eight queries in text2bpmn/checks/cq/ (with cq/pairs/alternatives.rq
for CQ6) run on it and on each configuration's saved ontology.owl. A
generated task label is replaced by the reference task compare.match_tasks
pairs it with, against that reference, as cq_compare does; so the keys of a
generated answer can differ between the two references.

cq_compare.py reads pilots laid out as <pilot>/case-<case>/; the release runs
are laid out as <experiment>/<case>/, which is why this is a script of its
own. Nothing is run again: the generated graphs are the release runs'.
"""
import argparse
import hashlib
from pathlib import Path

import rdflib

from text2bpmn.checks.common import header, provenance, write
from text2bpmn.checks.competency_questions import load_graph, queries, run
from text2bpmn.checks.cq_compare import ALTERNATIVES, compare_question, compare_sets, fmt, keys
from text2bpmn.checks.loan_rescore import CONFIGURATIONS, REFERENCES
from text2bpmn.checks.reference_reader import read_reference
from text2bpmn.compare import compare, normalise, read_bpmn
from text2bpmn.ontology import populate

CASE = "loan"
BBO_SHA256 = "91509c7ebb04bcda6628b140b86237365ddc8055799612f9f92a55a875b3de39"  # checks/fetch_bbo.py


def reference_answers(path, ontology, bbo, out):
    owl = Path(out) / "references" / Path(path).stem / "ontology.owl"
    model = read_reference(path, CASE)
    summary = populate(model, ontology, owl, validate=False)
    graph = load_graph(owl, bbo)
    qs = queries()
    return {"populated": summary, "participants": model["participants"],
            "answers": {n: run(graph, n, q) for n, q in qs.items()},
            "alternatives": run(graph, "cq6", ALTERNATIVES)["rows"]}


def per_question(reference, reference_path, folder, bbo):
    """cq_compare.main's comparison for one generated graph against one reference."""
    matched = compare(read_bpmn(reference_path), read_bpmn(Path(folder) / "model.bpmn"))["mapping"]
    to_reference = {normalise(g): normalise(r) for r, g in matched}
    gen_task = lambda label: to_reference.get(normalise(label), f"(unmatched) {normalise(label)}")
    graph = load_graph(Path(folder) / "ontology.owl", bbo)
    qs = queries()
    answers = {n: run(graph, n, q) for n, q in qs.items()}
    alternatives = run(graph, "cq6", ALTERNATIVES)["rows"]
    out = {}
    ref_participants = int(reference["answers"]["cq8"]["rows"][0]["participants"])
    for n in qs:
        if n == "cq8":
            ref_row, gen_row = reference["answers"][n]["rows"][0], answers[n]["rows"][0]
            out[n] = {"counts": {k: {"reference": int(ref_row[k]), "generated": int(gen_row[k])} for k in ref_row}}
        elif n == "cq6":
            out[n] = compare_sets(keys(n, reference["alternatives"], normalise), keys(n, alternatives, gen_task))
        else:
            out[n] = compare_question(n, keys(n, reference["answers"][n]["rows"], normalise),
                                      keys(n, answers[n]["rows"], gen_task), ref_participants)
    return {"task_matches": matched, "answers": answers, "comparison": out}


def show(key):
    """A key as text: an unordered pair as {a, b}, a tuple as (a, b, ...)."""
    if isinstance(key, frozenset):
        return "{" + ", ".join(sorted(key)) + "}"
    if isinstance(key, tuple):
        return "(" + ", ".join(part for part in key if part) + ")"
    return str(key)


def reference_keys(reference):
    """Each question's answer on the reference itself, as the keys it is scored on."""
    out = {}
    for n in queries():
        if n == "cq8":
            out[n] = reference["answers"][n]["rows"][0]
        elif n == "cq6":
            out[n] = sorted(map(show, keys(n, reference["alternatives"], normalise)))
        else:
            out[n] = sorted(map(show, keys(n, reference["answers"][n]["rows"], normalise)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ontology", default="BPMNbasedOntologyV1_2.owl",
                    help="BBO, as text2bpmn/checks/fetch_bbo.py fetches it (read only)")
    ap.add_argument("--out", default="runs/checks/final-3/loan_reference/cq")
    args = ap.parse_args()
    digest = hashlib.sha256(Path(args.ontology).read_bytes()).hexdigest()
    if digest != BBO_SHA256:
        raise SystemExit(f"{args.ontology}: SHA-256 {digest}, not the pinned {BBO_SHA256}")
    bbo = rdflib.Graph().parse(args.ontology)
    qs = queries()
    record = provenance(ontology=args.ontology, ontology_sha256=digest,
                        references=dict(REFERENCES), configurations=dict(CONFIGURATIONS))
    result = {"provenance": record, "references": {}, "configurations": {}}
    for name, path in REFERENCES:
        ref = reference_answers(path, args.ontology, bbo, args.out)
        result["references"][name] = {"path": path, **ref, "keys": reference_keys(ref)}
    for config, folder in CONFIGURATIONS:
        result["configurations"][config] = {
            "folder": folder,
            **{name: per_question(result["references"][name], path, folder, bbo) for name, path in REFERENCES}}

    lines = header("Loan competency answers: the textbook reference (D12) beside the authored one", record)
    lines += ["As text2bpmn/checks/cq_compare.py, for the loan case: each cell is both / reference / generated, "
              "with precision and recall; CQ2 and CQ6 count unordered pairs of alternative tasks; CQ8 gives "
              "reference / generated for tasks, decisions, parallel blocks and participants; n/a: CQ1 or CQ5 (about "
              "participants) against a reference that has none. Tasks are matched "
              "by text2bpmn.compare.match_tasks against the reference of the row. `authored` is "
              "reference_authored.bpmn (the reference of runs/checks/cq_compare), `textbook` is reference.bpmn.",
              "", "## The references' own answers", "",
              "| question | authored | textbook |", "|---|---|---|"]
    for n in qs:
        cells = []
        for name in ("authored", "textbook"):
            k = result["references"][name]["keys"][n]
            if n == "cq8":
                cells.append(", ".join(f"{key} {value}" for key, value in k.items()))
            else:
                cells.append(f"{len(k)}: " + "; ".join(k) if k else "0 (empty: "
                             + result["references"][name]["answers"][n].get("empty_because", "") + ")")
        lines.append(f"| {n} {qs[n]['question'][4:]} | " + " | ".join(cells) + " |")
    lines += ["", "## Generated against each reference", "",
              "| configuration | reference | " + " | ".join(qs) + " |", "|---" * (len(qs) + 2) + "|"]
    changed = []
    for config, entry in result["configurations"].items():
        for name in ("authored", "textbook"):
            per = entry[name]["comparison"]
            lines.append(f"| {config} | {name} | " + " | ".join(fmt(per[n]) for n in qs) + " |")
        for n in qs:
            a, b = fmt(entry["authored"]["comparison"][n]), fmt(entry["textbook"]["comparison"][n])
            if a != b:
                changed.append(f"- {config}, {n}: {a} -> {b}")
    lines += ["", "## What changes from the authored to the textbook reference", ""] + (changed or ["- nothing"])
    print("wrote", write(args.out, "loan_cq", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
