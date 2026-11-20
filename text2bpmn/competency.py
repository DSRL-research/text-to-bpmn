"""Competency questions against a populated ontology.

    python3 -m text2bpmn.competency ONTOLOGY.owl [--out report.md]
    python3 -m text2bpmn.competency EXTRACTION.json   # populates a copy first

Each question is one stored SPARQL query, so what the graph can answer is
stated as queries rather than claimed in prose. They are the questions the
graph can answer and the diagram cannot: which actor performs a step, which
steps run concurrently, which branch is the alternative one, and -- the useful
negative -- which decisions have no alternative branch at all, which is a fault
in the model that no amount of reading the picture makes obvious.

The relation each edge came from and the actors are both in the ontology only
because text2bpmn/ontology.py puts them there; before that every edge was a
bare SequenceFlow and lanes never reached the OWL file.
"""
import argparse
import tempfile
from pathlib import Path

import rdflib

PREFIXES = """
PREFIX b: <http://BPMNbasedOntology#>
PREFIX t: <http://text2bpmn.local/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

QUESTIONS = [
    ("Who performs each activity?",
     ["Activity", "Actor"],
     """SELECT ?activity ?actor WHERE {
            ?task a b:Task ; rdfs:label ?activity ; b:has_resource ?resource .
            ?resource rdfs:label ?actor .
        } ORDER BY ?actor ?activity"""),

    ("How many activities does each actor perform?",
     ["Actor", "Activities"],
     """SELECT ?actor (COUNT(?task) AS ?activities) WHERE {
            ?task a b:Task ; b:has_resource ?resource .
            ?resource rdfs:label ?actor .
        } GROUP BY ?actor ORDER BY DESC(?activities)"""),

    ("Which activities run concurrently?",
     ["Split", "Activity"],
     # only the edges that leave a split: a parallel block also has an edge
     # from each member into its join, which is the same pair backwards
     """SELECT ?split ?activity WHERE {
            ?flow a t:ParallelFlow ; b:has_sourceRef ?gateway ; b:has_targetRef ?target .
            ?gateway a b:ParallelGateway .
            ?target a b:Task ; rdfs:label ?activity .
            BIND(STRAFTER(STR(?gateway), "#") AS ?split)
        } ORDER BY ?split ?activity"""),

    ("What does each decision's branches lead to, and under what condition?",
     ["Decision", "Condition", "Leads to"],
     """SELECT ?decision ?condition ?target WHERE {
            ?flow b:has_sourceRef ?gateway ; b:has_targetRef ?node ; t:extracted_relation ?relation .
            ?gateway a b:ExclusiveGateway ; rdfs:label ?decision .
            ?node rdfs:label ?target .
            OPTIONAL { ?flow t:branch_condition ?label }
            BIND(COALESCE(?label, ?relation) AS ?condition)
        } ORDER BY ?decision ?condition"""),

    ("Which step is the alternative (false) branch?",
     ["Decision", "Alternative"],
     """SELECT ?decision ?alternative WHERE {
            ?flow a t:FalseBranchFlow ; b:has_sourceRef ?gateway ; b:has_targetRef ?node .
            ?gateway rdfs:label ?decision .
            ?node rdfs:label ?alternative .
        } ORDER BY ?decision"""),

    ("Which decisions have no alternative branch? (a fault, not a feature)",
     ["Decision"],
     # only a split can be missing a branch: a gateway with one outgoing edge is
     # a join, and the Validation Layer removes a decision that has just one
     """SELECT ?decision WHERE {
            ?gateway a b:ExclusiveGateway ; rdfs:label ?decision .
            {
                SELECT ?gateway (COUNT(?next) AS ?branches) WHERE {
                    ?gateway b:has_nextFlowNode ?next .
                } GROUP BY ?gateway
            }
            FILTER(?branches > 1)
            FILTER NOT EXISTS { ?flow a t:FalseBranchFlow ; b:has_sourceRef ?gateway }
        } ORDER BY ?decision"""),

    ("Which actors hand work to one another?",
     ["From", "To", "Handovers"],
     # a handover is the next activity after this one, reached directly or
     # across one gateway, since a decision or a join is not itself work
     """SELECT ?from ?to (COUNT(*) AS ?handovers) WHERE {
            ?source a b:Task ; b:has_resource ?performer .
            ?target a b:Task ; b:has_resource ?receiver .
            {
                ?source b:has_nextFlowNode ?target .
            } UNION {
                ?source b:has_nextFlowNode ?gateway .
                ?gateway b:has_nextFlowNode ?target .
                FILTER NOT EXISTS { ?gateway a b:Task }
            }
            ?performer rdfs:label ?from .
            ?receiver rdfs:label ?to .
            FILTER(?from != ?to)
        } GROUP BY ?from ?to ORDER BY DESC(?handovers)"""),
]


BBO_FILE = "BPMNbasedOntologyV1_2.owl"


def load(path):
    """The graph for an ontology file, or for an extraction populated into one."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        from text2bpmn.load import load_extraction
        from text2bpmn.ontology import populate
        out = Path(tempfile.mkdtemp()) / f"{path.parent.name or path.stem}.owl"
        populate(load_extraction(path), "BPMNbasedOntologyV1_2.owl", out)
        path = out
    graph = rdflib.Graph()
    # the populated file holds the individuals and imports BBO, so BBO is
    # loaded beside it when present (text2bpmn/checks/fetch_bbo.py fetches it)
    if Path(BBO_FILE).exists():
        graph.parse(BBO_FILE)
    graph.parse(str(path))
    return graph, path


def ask(graph):
    """Every question's rows, in order."""
    out = []
    for question, columns, query in QUESTIONS:
        rows = [[str(value) if value is not None else "" for value in row]
                for row in graph.query(PREFIXES + query)]
        out.append({"question": question, "columns": columns, "rows": rows})
    return out


def to_markdown(results, source):
    lines = [f"# Competency questions: `{source}`", ""]
    for result in results:
        lines += [f"## {result['question']}", ""]
        if not result["rows"]:
            lines += ["(no answer in this model)", ""]
            continue
        lines += ["| " + " | ".join(result["columns"]) + " |",
                  "|" + "---|" * len(result["columns"])]
        for row in result["rows"]:
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ontology", help="populated .owl file, or a finder3 extraction .json")
    ap.add_argument("--out", help="write the report here as well as printing it")
    args = ap.parse_args()
    graph, source = load(args.ontology)
    text = to_markdown(ask(graph), source.name)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"✅ Wrote {args.out}")


if __name__ == "__main__":
    main()
