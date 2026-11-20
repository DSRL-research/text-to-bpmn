"""Task 5: competency questions over the populated BBO graphs, in SPARQL.

    ~/.venvs/checks-env/bin/python -m text2bpmn.checks.competency_questions \
        runs/pilot runs/pilot_scripted [--documents case-loan case-goods_dispatch case-healthcare]

The queries are text2bpmn/checks/cq/cq1.rq ... cq8.rq. They use only what the
graph holds. Each graph is the fetched BBO plus the populated file, which
holds only the individuals and imports BBO by IRI.

Per graph and query: the answer rows and the time taken. A query that returns
nothing is classified by a precondition: either the model has no such
construct, or it has one and still no row satisfies the question -- for
example a false outcome that leads straight to a join, with no task of its
own. Every precondition reads only predicates the graph holds, so an empty
answer is never a missing triple the query depends on.
"""
import argparse
import time
from pathlib import Path

import rdflib

from text2bpmn.checks.common import header, provenance, write

CQ = Path(__file__).parent / "cq"
BBO_FILE = Path("BPMNbasedOntologyV1_2.owl")  # fetched by text2bpmn/checks/fetch_bbo.py
PREFIXES = """PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""
DECISION = "{ SELECT ?g WHERE { ?g a b:ExclusiveGateway . ?f b:has_sourceRef ?g } GROUP BY ?g HAVING (COUNT(?f) >= 2) }"
# what each question needs the model to contain, as an ASK, and what it is called
PRECONDITIONS = {
    "cq1": ("ASK { ?t a b:Task }", "task"),
    "cq2": (f"ASK {DECISION}", "decision (exclusive split)"),
    "cq3": ("ASK { ?p a b:ParallelGateway . ?f1 b:has_sourceRef ?p . ?f2 b:has_sourceRef ?p . FILTER(?f1 != ?f2) }",
            "parallel split"),
    "cq4": ("ASK { ?t a b:Task }", "task"),
    "cq5": ("ASK { ?a b:has_resource ?r1 . ?c b:has_resource ?r2 . ?a a b:Task . ?c a b:Task . FILTER(?r1 != ?r2) }",
            "pair of tasks in different lanes"),
    "cq6": ('ASK { ?f b:has_sourceRef ?g . { ?f t:extracted_relation ?r . FILTER(STR(?r) = "FALSE_BRANCH") } '
            'UNION { ?f t:branch_condition ?c . FILTER(STR(?c) = "No") } }', "false outcome of a decision"),
    "cq7": (f"ASK {DECISION}", "decision (exclusive split)"),
    "cq8": ("ASK { }", "anything"),
}


def load_graph(path, bbo=None):
    """BBO plus the individuals file: the populated file imports BBO by IRI
    and holds only what the pipeline adds."""
    if bbo is None:
        if not BBO_FILE.exists():
            raise SystemExit(f"{BBO_FILE} is missing: run python3 -m text2bpmn.checks.fetch_bbo first")
        bbo = rdflib.Graph().parse(BBO_FILE)
    graph = rdflib.Graph()
    graph += bbo
    graph.parse(path)
    return graph


def queries():
    out = {}
    for path in sorted(CQ.glob("cq*.rq")):
        text = path.read_text(encoding="utf-8")
        out[path.stem] = {"question": text.splitlines()[0].lstrip("# ").strip(), "text": text}
    return out


def run(graph, name, query):
    start = time.perf_counter()
    result = graph.query(query["text"])
    rows = [{str(v): (str(row[v]) if row[v] is not None else None) for v in result.vars} for row in result]
    seconds = round(time.perf_counter() - start, 3)
    answer = {"rows": rows, "count": len(rows), "seconds": seconds}
    if not rows:
        ask, needs = PRECONDITIONS[name]
        present = bool(graph.query(PREFIXES + ask).askAnswer)
        answer["empty_because"] = (f"the model has a {needs} and the graph holds what the query reads, "
                                   f"but no row satisfies the question" if present
                                   else f"no such construct in the model (no {needs})")
    return answer


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--documents", nargs="+", default=["case-loan", "case-goods_dispatch", "case-healthcare"])
    ap.add_argument("--out", default="runs/checks/competency")
    args = ap.parse_args()
    qs = queries()
    bbo = rdflib.Graph().parse(BBO_FILE) if BBO_FILE.exists() else None
    record = provenance(bbo=str(BBO_FILE), folders=args.folders, documents=args.documents,
                        queries={k: v["question"] for k, v in qs.items()})
    result = {"provenance": record, "graphs": {}}
    lines = header("Competency questions over the populated BBO graphs", record)
    lines += ["| CQ | question |", "|---|---|"] + [f"| {k} | {v['question'][4:]} |" for k, v in qs.items()] + [""]
    for folder in args.folders:
        lines += [f"## {folder}", "", "| graph | " + " | ".join(qs) + " |", "|---" * (len(qs) + 1) + "|"]
        empties = []
        for doc in args.documents:
            path = Path(folder) / doc / "ontology.owl"
            graph = load_graph(path, bbo)
            answers = {name: run(graph, name, q) for name, q in qs.items()}
            result["graphs"][f"{folder}/{doc}"] = answers
            lines.append(f"| {doc} | " + " | ".join(f"{a['count']} ({a['seconds']} s)" for a in answers.values()) + " |")
            empties += [f"- {doc} {name}: {a['empty_because']}" for name, a in answers.items() if "empty_because" in a]
        lines += ["", "Rows returned (time). Empty answers:", ""] + (empties or ["- none"]) + [""]
    print("wrote", write(args.out, "competency_questions", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
