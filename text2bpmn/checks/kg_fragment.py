"""A fragment of the loan case's populated knowledge graph, for Section 3.3.6.

    python3 -m text2bpmn.checks.kg_fragment [--owl PATH]
        # -> figures/section_3_3_6/loan_kg_fragment.{ttl,dot,svg,png}
        #    runs/checks/final-3/open_analyses/kg_fragment.{md,json}

The graph is the release run's (runs/final-3/cases/loan/ontology.owl, commit
41df7c1, written at revision-final-3). The triples are selected from the file
with rdflib and serialised as they are, nothing retyped:

- the ontology header: the process's owl:Ontology and its owl:imports of BBO
  (http://BPMNbasedOntology), with the file's prefixes;
- the class axioms that make TrueBranchFlow and FalseBranchFlow BBO
  SequenceFlows (rdfs:subClassOf);
- the eligibility decision: its type and rdfs:label, and its has_outgoing;
- its two outgoing flows: type, has_sourceRef, has_targetRef, and their labels
  (the file gives a flow no rdfs:label; its name is onto:branch_condition, beside
  onto:extracted_relation);
- the Yes flow's target task: type, label and has_resource, and that
  HumanResource's type and label (the task's lane); and the No flow's target's label.

owl:NamedIndividual typings and has_container / has_next / has_previous links are
left out. Every triple of the written Turtle is checked against the file, after
parsing the Turtle back. The diagram is drawn by graphviz `dot` from the same
triples: individuals as ellipses, classes as rounded boxes, literals as boxes,
each edge labelled with its property; black on white.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import rdflib
from rdflib import OWL, RDF, RDFS, XSD, Literal, URIRef

OWL_FILE = "runs/final-3/cases/loan/ontology.owl"
FIG = Path("figures/section_3_3_6/loan_kg_fragment")
OUT = Path("runs/checks/final-3/open_analyses/kg_fragment")
BPMN = rdflib.Namespace("http://BPMNbasedOntology#")
ONTO = rdflib.Namespace("http://text2bpmn.local/ontology#")


def select(g):
    ontology = next(g.subjects(RDF.type, OWL.Ontology))
    proc = rdflib.Namespace(str(ontology) + "#")
    gateways = [s for s in g.subjects(RDF.type, BPMN.ExclusiveGateway)
                if "eligible" in str(g.value(s, RDFS.label) or "")]
    assert len(gateways) == 1, gateways
    gateway = gateways[0]
    flows = sorted(g.subjects(BPMN.has_sourceRef, gateway))
    assert len(flows) == 2, flows
    kinds = {f: next(t for t in g.objects(f, RDF.type) if t in (ONTO.TrueBranchFlow, ONTO.FalseBranchFlow))
             for f in flows}
    true_flow = next(f for f in flows if kinds[f] == ONTO.TrueBranchFlow)
    false_flow = next(f for f in flows if kinds[f] == ONTO.FalseBranchFlow)
    task = g.value(true_flow, BPMN.has_targetRef)
    resource = g.value(task, BPMN.has_resource)
    other = g.value(false_flow, BPMN.has_targetRef)

    triples = [(ontology, RDF.type, OWL.Ontology), *((ontology, OWL.imports, o) for o in g.objects(ontology, OWL.imports)),
               (ONTO.TrueBranchFlow, RDFS.subClassOf, BPMN.SequenceFlow),
               (ONTO.FalseBranchFlow, RDFS.subClassOf, BPMN.SequenceFlow),
               (gateway, RDF.type, BPMN.ExclusiveGateway), (gateway, RDFS.label, g.value(gateway, RDFS.label)),
               *((gateway, BPMN.has_outgoing, f) for f in (true_flow, false_flow))]
    for f in (true_flow, false_flow):
        triples += [(f, RDF.type, kinds[f]), (f, BPMN.has_sourceRef, gateway),
                    (f, BPMN.has_targetRef, g.value(f, BPMN.has_targetRef)),
                    (f, ONTO.branch_condition, g.value(f, ONTO.branch_condition)),
                    (f, ONTO.extracted_relation, g.value(f, ONTO.extracted_relation))]
    triples += [(task, RDF.type, BPMN.Task), (task, RDFS.label, g.value(task, RDFS.label)),
                (task, BPMN.has_resource, resource),
                (resource, RDF.type, BPMN.HumanResource), (resource, RDFS.label, g.value(resource, RDFS.label)),
                (other, RDFS.label, g.value(other, RDFS.label))]
    assert all(o is not None for _, _, o in triples)
    fragment = rdflib.Graph(bind_namespaces="none")
    for prefix, namespace in (("rdf", RDF), ("rdfs", RDFS), ("owl", OWL), ("xsd", XSD), ("BPMN", BPMN),
                              ("onto", ONTO), ("proc", proc)):
        fragment.bind(prefix, namespace)
    for t in triples:
        fragment.add(t)
    assert len(fragment) == len(triples)
    return fragment, {"ontology": str(ontology), "gateway": str(gateway), "true_flow": str(true_flow),
                      "false_flow": str(false_flow), "task": str(task), "resource": str(resource)}


def qname(graph, term):
    if isinstance(term, Literal):
        return f'"{term}"'
    try:
        return graph.namespace_manager.normalizeUri(term)
    except Exception:
        return f"<{term}>"


def dot_source(fragment):
    classes = {o for _, p, o in fragment if p in (RDF.type, RDFS.subClassOf)} | \
              {s for s, p, _ in fragment if p == RDFS.subClassOf}
    ids, lines = {}, ['digraph kg {', '  graph [rankdir=LR, bgcolor="white", fontname="DejaVu Sans", nodesep=0.25, '
                      'ranksep=0.45, pad=0.15];',
                      '  node [fontname="DejaVu Sans", fontsize=11, color="black", fontcolor="black", penwidth=1];',
                      '  edge [fontname="DejaVu Sans", fontsize=9, color="black", fontcolor="black", arrowsize=0.7];']

    def node(term):
        if term not in ids:
            ids[term] = f"n{len(ids)}"
            label = qname(fragment, term).replace('"', '\\"')
            if isinstance(term, Literal):
                shape = 'shape=box'
            elif term in classes:
                shape = 'shape=box, style="rounded"'
            elif term == URIRef("http://BPMNbasedOntology"):
                shape = 'shape=box, style="rounded,dashed"'
            else:
                shape = 'shape=ellipse'
            lines.append(f'  {ids[term]} [label="{label}", {shape}];')
        return ids[term]

    for s, p, o in sorted(fragment, key=lambda t: (str(t[0]), str(t[1]), str(t[2]))):
        a, b = node(s), node(o)
        label = "a" if p == RDF.type else qname(fragment, p)
        # has_sourceRef runs back to the gateway: drawn, but not used to rank, so the
        # gateway stands before both of its flows
        extra = ", constraint=false" if p == BPMN.has_sourceRef else ""
        lines.append(f'  {a} -> {b} [label="{label}"{extra}];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--owl", default=OWL_FILE, help="the release run's loan ontology.owl")
    args = ap.parse_args()
    data = Path(args.owl).read_bytes()
    g = rdflib.Graph()
    g.parse(data=data, format="xml")
    fragment, picked = select(g)

    FIG.parent.mkdir(parents=True, exist_ok=True)
    header = (f"# A fragment of the loan case's knowledge graph (release run, revision-final-3):\n"
              f"# {len(fragment)} triples selected from runs/final-3/cases/loan/ontology.owl\n"
              f"# (sha256 {hashlib.sha256(data).hexdigest()}) by text2bpmn/checks/kg_fragment.py.\n")
    FIG.with_suffix(".ttl").write_text(header + fragment.serialize(format="turtle"), encoding="utf-8")

    # check: the Turtle parsed back is the selection, and every triple is in the file
    back = rdflib.Graph()
    back.parse(FIG.with_suffix(".ttl"), format="turtle")
    in_file = sum(t in g for t in back)
    assert set(back) == set(fragment) and in_file == len(back), "a fragment triple is not in the file"

    FIG.with_suffix(".dot").write_text(dot_source(fragment), encoding="utf-8")
    subprocess.run(["dot", "-Tsvg", str(FIG.with_suffix(".dot")), "-o", str(FIG.with_suffix(".svg"))], check=True)
    subprocess.run(["dot", "-Tpng", "-Gdpi=300", str(FIG.with_suffix(".dot")), "-o", str(FIG.with_suffix(".png"))],
                   check=True)
    # dot draws at 300 dpi but leaves the alpha channel and no dpi in the file: flatten on white, record 300 dpi
    from PIL import Image
    drawn = Image.open(FIG.with_suffix(".png")).convert("RGBA")
    flat = Image.new("RGBA", drawn.size, "white")
    flat.alpha_composite(drawn)
    flat.convert("RGB").save(FIG.with_suffix(".png"), dpi=(300, 300))
    version = subprocess.run(["dot", "-V"], capture_output=True, text=True).stderr.strip()

    report = {"source": OWL_FILE, "source_sha256": hashlib.sha256(data).hexdigest(), "triples_in_file": len(g),
              "fragment_triples": len(fragment), "fragment_triples_found_in_file": in_file, "selected": picked,
              "files": [str(FIG.with_suffix(x)) for x in (".ttl", ".dot", ".svg", ".png")], "graphviz": version,
              "rdflib": rdflib.__version__}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT.with_suffix(".md").write_text(
        "# Knowledge-graph fragment for Section 3.3.6 (loan, release run)\n\n"
        f"Generated by `text2bpmn/checks/kg_fragment.py`. Source `{OWL_FILE}` (sha256 {report['source_sha256']}, "
        f"{len(g)} triples). Fragment: {len(fragment)} triples, **{in_file}/{len(fragment)} found in the file** "
        "after parsing the written Turtle back.\n\n"
        + "".join(f"- {k}: `{v}`\n" for k, v in picked.items())
        + f"\nFiles: {', '.join(f'`{f}`' for f in report['files'])} ({version}; PNG at 300 dpi).\n\n"
        "```turtle\n" + FIG.with_suffix(".ttl").read_text(encoding="utf-8") + "```\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
