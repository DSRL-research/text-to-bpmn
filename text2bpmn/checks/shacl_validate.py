"""Task 4: validate every populated ontology against BBO's own SHACL shapes.

    ~/.venvs/checks-env/bin/python -m text2bpmn.checks.shacl_validate runs/pilot [runs/pilot_scripted ...]

Shapes: text2bpmn/checks/shacl/SHACLshapes.ttl, fetched from the BBO
repository at a pinned commit by text2bpmn/checks/fetch_bbo.py (GPL-3.0, so
not committed here). Data graph: each <doc>/ontology.owl, which holds the
process's individuals and imports BBO by IRI. Ontology graph: BBO itself
(BPMNbasedOntologyV1_2.owl, fetched the same way), which pyshacl mixes into
the data graph so that class hierarchies are respected, with inference="rdfs".

Per graph: conforms or not, and the violations grouped by shape and focus
node. Each graph is validated a second time with inference="both" (RDFS plus
OWL RL), which applies owl:inverseOf: a violation that disappears there is
one whose information the graph holds only through an inverse property. A violation whose focus node is an individual the population created --
one that is not in BBO's own file -- comes from the population; one on a node
that BBO already contains does not.

Needs pyshacl (requirements.txt pins it).
"""
import argparse
import time
from collections import Counter, defaultdict
from pathlib import Path

import rdflib
from pyshacl import validate
from rdflib.namespace import RDF, SH

from text2bpmn.checks.common import documents, header, provenance, write

HERE = Path(__file__).parent
SHAPES = HERE / "shacl" / "SHACLshapes.ttl"
ONTOLOGY = Path("BPMNbasedOntologyV1_2.owl")


def short(term):
    text = str(term)
    return text.split("#")[-1] if "#" in text else text.rsplit("/", 1)[-1]


def violations(report, shapes, own_subjects):
    found = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        get = lambda p: report.value(result, p)
        focus = get(SH.focusNode)
        found.append({"shape": short(get(SH.sourceShape)) if isinstance(get(SH.sourceShape), rdflib.URIRef)
                      else short(next(shapes.subjects(SH.property, get(SH.sourceShape)), "(anonymous)")),
                      "component": short(get(SH.sourceConstraintComponent)),
                      "path": short(get(SH.resultPath)) if get(SH.resultPath) else None,
                      "focus": short(focus), "value": short(get(SH.value)) if get(SH.value) else None,
                      "message": str(get(SH.resultMessage)),
                      "origin": "BBO itself" if focus in own_subjects else "our population"})
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--out", default="runs/checks/shacl")
    args = ap.parse_args()
    if not SHAPES.exists():
        raise SystemExit(f"{SHAPES} is missing: run python3 -m text2bpmn.checks.fetch_bbo first")
    shapes = rdflib.Graph().parse(SHAPES)
    if not ONTOLOGY.exists():
        raise SystemExit(f"{ONTOLOGY} is missing: run python3 -m text2bpmn.checks.fetch_bbo first")
    ontology = rdflib.Graph().parse(ONTOLOGY)
    bbo_subjects = set(ontology.subjects())
    record = provenance(shapes=str(SHAPES), ontology=str(ONTOLOGY), inference="rdfs", folders=args.folders,
                        shapes_triples=len(shapes), ontology_triples=len(ontology))
    result = {"provenance": record, "folders": {}}
    lines = header("SHACL validation with BBO's shapes", record)
    for folder in args.folders:
        graphs = {}
        for doc, path in documents(folder, "ontology.owl"):
            start = time.perf_counter()
            data = rdflib.Graph().parse(path)
            conforms, report, _ = validate(data, shacl_graph=shapes, ont_graph=ontology,
                                           inference="rdfs", abort_on_first=False)
            found = violations(report, shapes, bbo_subjects)
            owl_rl_conforms, owl_rl_report, _ = validate(data, shacl_graph=shapes, ont_graph=ontology,
                                                         inference="both", abort_on_first=False)
            owl_rl = Counter((v["shape"], v["component"], v["path"])
                             for v in violations(owl_rl_report, shapes, bbo_subjects))
            groups = Counter((v["shape"], v["component"], v["path"], v["origin"]) for v in found)
            graphs[doc] = {"conforms": conforms, "triples": len(data), "violations": len(found),
                           "conforms_with_owl_rl": owl_rl_conforms,
                           "violations_with_owl_rl": sum(owl_rl.values()),
                           "seconds": round(time.perf_counter() - start, 2),
                           "by_shape": [{"shape": s, "component": c, "path": p, "origin": o, "count": n}
                                        for (s, c, p, o), n in groups.most_common()],
                           "results": found}
        total = Counter()
        focus = defaultdict(set)
        for doc, g in graphs.items():
            for v in g["results"]:
                key = (v["shape"], v["component"], v["path"], v["origin"])
                total[key] += 1
                focus[key].add(f"{doc}:{v['focus']}")
        conforming = sum(g["conforms"] for g in graphs.values())
        conforming_rl = sum(g["conforms_with_owl_rl"] for g in graphs.values())
        result["folders"][folder] = {"graphs": len(graphs), "conforming": conforming,
                                     "conforming_with_owl_rl": conforming_rl,
                                     "groups": [{"shape": s, "component": c, "path": p, "origin": o,
                                                 "violations": n, "focus_nodes_example": sorted(focus[(s, c, p, o)])[:5]}
                                                for (s, c, p, o), n in total.most_common()],
                                     "per_graph": graphs}
        lines += [f"## {folder}", "", f"{conforming} of {len(graphs)} graphs conform with RDFS inference, "
                  f"{conforming_rl} with RDFS plus OWL RL "
                  f"({sum(g['violations_with_owl_rl'] for g in graphs.values())} violations left).", ""]
        if total:
            lines += ["| shape | constraint | path | origin | violations | graphs |", "|---|---|---|---|---|---|"]
            for (s, c, p, o), n in total.most_common():
                docs = len({f.split(':')[0] for f in focus[(s, c, p, o)]})
                lines.append(f"| {s} | {c} | {p} | {o} | {n} | {docs} |")
            lines.append("")
    print("wrote", write(args.out, "shacl_validation", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
