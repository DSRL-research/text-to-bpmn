"""Populate a BPMN 2.0 ontology from an extraction.

    python3 -m text2bpmn.ontology EXTRACTION -o OUT.owl [--ontology FILE]

Ported out of finder3.py so the step runs from a saved extraction, without the
entity recogniser, the coreference model or the LLM, and so that the competency
questions in text2bpmn/competency.py have something to query.

Two things the populated copy now holds that it did not before:

- **The relation each edge came from.** Every edge became a bare SequenceFlow,
  so TRUE_BRANCH, FALSE_BRANCH and PARALLEL were lost at the ontology boundary
  and no query could ask which branch is the alternative one. The extraction
  records the relation per flow, and it is written both as a data property and
  as a subclass of SequenceFlow, so a query can filter either way.
- **The actors.** Lanes never reached the OWL file at all. This ontology is
  BBO, the BPMN-based Ontology of Annane, Aussenac and Kamel (MELODI, IRIT
  Toulouse, 2019; versionInfo 1.0, whatever the file name's "V1_2" suggests).
  It formalises the process fragment of BPMN 2.0 and has no Lane or
  Participant class; the performer of work is a resource. Each lane therefore
  becomes a HumanResource -- a subclass of Agent and Resource -- linked from
  its activities with has_resource, whose range is Resource.

Properties and classes this pipeline adds live in their own namespace, so
nothing it writes claims to be part of the imported ontology.

The output file holds only what this pipeline adds -- the process's
individuals and those few classes and properties -- in an ontology of its own
that owl:imports BBO by its IRI, http://BPMNbasedOntology. BBO (GPL-3.0) is
not copied into it; a reader loads BBO beside it (text2bpmn/checks/fetch_bbo.py
fetches the pinned file). BBO is read from a temporary copy without its
unreachable UO import, never written next to the output.
"""
import argparse
import json
import tempfile
import types
import uuid
from collections import Counter
from pathlib import Path

import rdflib
from owlready2 import DataProperty, World

from text2bpmn import structure
from text2bpmn.load import load_extraction

BBO = "http://BPMNbasedOntology#"
BBO_IRI = "http://BPMNbasedOntology"
EXTRA_NAMESPACE = "http://text2bpmn.local/ontology#"
# each populated process is an ontology of its own under this IRI
PROCESS_NAMESPACE = "http://text2bpmn.local/process/"
# Property pairs BBO declares owl:inverseOf. owlready2 saves one triple per
# pair, so the file held Process has_flowElements X but never X has_container
# Process, and none of has_outgoing, has_incoming and has_previousFlowNode at
# all; BBO's own SHACL shape requires has_container on every flow element.
# Both directions are written after saving, so the file needs no OWL reasoner
# to answer either.
INVERSE_PAIRS = (("has_flowElements", "has_container"), ("has_sourceRef", "has_outgoing"),
                 ("has_targetRef", "has_incoming"), ("has_nextFlowNode", "has_previousFlowNode"))
# the ontology imports a URL that 404s, which stops it loading offline
FAILING_IMPORT = '<owl:imports rdf:resource="http://purl.obolibrary.org/obo/uo/releases/2018-05-20/uo.owl"/>'
RELATIONS = ("SEQUENCE", "TRUE_BRANCH", "FALSE_BRANCH", "PARALLEL", "CONDITION_DEF")


def _offline_copy(ontology_file, directory):
    """A copy of the ontology without the failing import, in `directory`, so a
    run never modifies the file it was given."""
    text = Path(ontology_file).read_text(encoding="utf-8")
    if FAILING_IMPORT not in text:
        return str(ontology_file)
    copy = Path(directory) / Path(ontology_file).name
    copy.write_text(text.replace(FAILING_IMPORT, ""), encoding="utf-8")
    return str(copy)


def _class_for(onto, element_type):
    """The ontology class for an extracted element type, by what it really has."""
    names = {c.name for c in onto.classes()}
    preferred = {"startEvent": ("StartEvent",), "endEvent": ("EndEvent",),
                 "task": ("Task", "Activity"), "exclusiveGateway": ("ExclusiveGateway", "Gateway"),
                 "parallelGateway": ("ParallelGateway", "Gateway"),
                 # the pipeline never builds one; reference models have them
                 "inclusiveGateway": ("InclusiveGateway", "Gateway")}
    for name in preferred.get(element_type, ()):
        if name in names:
            return getattr(onto, name)
    return onto.FlowElement


def _link(individual, prop, value, available):
    """Set a property whether the ontology declares it functional or not: a
    functional property reads back as None, not as a list to append to."""
    if prop not in available:
        return
    current = getattr(individual, prop, None)
    if isinstance(current, list):
        current.append(value)
    else:
        setattr(individual, prop, value)


def _safe(text):
    """An IRI-safe local name."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in str(text))


def _write_inverses(out_file):
    """Add the missing direction of every INVERSE_PAIRS triple to the saved file."""
    graph = rdflib.Graph().parse(out_file)
    added = Counter()
    for forward, backward in INVERSE_PAIRS:
        p, q = rdflib.URIRef(BBO + forward), rdflib.URIRef(BBO + backward)
        for s, o in list(graph.subject_objects(p)):
            if (o, q, s) not in graph:
                graph.add((o, q, s))
                added[backward] += 1
        for s, o in list(graph.subject_objects(q)):
            if (o, p, s) not in graph:
                graph.add((o, p, s))
                added[forward] += 1
    graph.serialize(destination=str(out_file), format="xml")
    return dict(added)


def populate(process_data, ontology_file, out_file, validate=True):
    """Write the process's individuals, importing BBO, and return what went in.

    The extraction goes through the same Validation Layer as the diagram, so
    the ontology and the BPMN file describe one model and name one set of
    actors. Populated from the raw extraction, the ontology had both "The
    Hospital" and "Hospital" as performers, and a "Main Process" actor that no
    lane in the diagram corresponds to.

    validate=False populates a model that is BPMN already, such as a reference
    model read from its XML, as it stands: only rule 1's cleaning of ids and
    names is applied, none of the rules that would restructure it.
    """
    if not Path(ontology_file).exists():
        raise FileNotFoundError(f"{ontology_file}: fetch BBO first with python3 -m text2bpmn.checks.fetch_bbo")
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)

    process_model = structure.validate(process_data) if validate else structure.build(process_data)
    world = World()
    with tempfile.TemporaryDirectory() as directory:
        onto = world.get_ontology(_offline_copy(ontology_file, directory)).load()
    # what is written: an ontology of its own, importing BBO
    out = world.get_ontology(f"{PROCESS_NAMESPACE}{uuid.uuid4().hex[:8]}")
    out.imported_ontologies.append(onto)
    extra = out.get_namespace(EXTRA_NAMESPACE)
    with extra:
        extracted_relation = types.new_class("extracted_relation", (DataProperty,))
        extracted_relation.range = [str]
        branch_condition = types.new_class("branch_condition", (DataProperty,))
        branch_condition.range = [str]
        # one SequenceFlow subclass per branch relation, so a query can select
        # the alternative branches without string matching. A plain sequence
        # edge stays the ontology's own SequenceFlow.
        flow_classes = {r: types.new_class(f"{r.title().replace('_', '')}Flow", (onto.SequenceFlow,))
                        for r in RELATIONS if r != "SEQUENCE"}

    available = {p.name for p in onto.properties()}
    summary = {"out": str(out_file), "ontology_iri": out.base_iri.rstrip("#"), "imports": BBO_IRI,
               "classes": Counter(), "relations": Counter(), "lanes": {}}
    with out:
        process = onto.Process(f"Process_{uuid.uuid4().hex[:8]}")
        process.label = [str(process_data.get("name") or "Extracted process")]

        lanes = {}
        for name in sorted({n.lane for n in process_model.nodes.values() if n.lane}):
            individual = onto.HumanResource(f"Resource_{_safe(name)}")
            individual.label = [name]
            lanes[name] = individual
            summary["lanes"][name] = 0

        nodes = {}
        for node in process_model.nodes.values():
            ont_class = _class_for(onto, node.kind)
            individual = ont_class(_safe(node.id))
            individual.label = [node.name]
            for note in node.documentation:
                individual.comment.append(note)
            nodes[node.id] = individual
            summary["classes"][ont_class.name] += 1
            _link(process, "has_flowElements", individual, available)

            if node.lane in lanes:
                _link(individual, "has_resource", lanes[node.lane], available)
                summary["lanes"][node.lane] += 1

        for index, flow in enumerate(process_model.flows):
            source, target = nodes.get(flow.source), nodes.get(flow.target)
            if not (source and target):
                continue
            relation = flow.relation or "SEQUENCE"
            ont_class = flow_classes.get(relation, onto.SequenceFlow)
            individual = ont_class(f"Flow_{index}_{uuid.uuid4().hex[:4]}")
            individual.extracted_relation = [relation]
            if flow.name:
                individual.branch_condition = [flow.name]
            _link(individual, "has_sourceRef", source, available)
            _link(individual, "has_targetRef", target, available)
            _link(source, "has_outgoing", individual, available)
            _link(target, "has_incoming", individual, available)
            _link(source, "has_nextFlowNode", target, available)
            _link(target, "has_previousFlowNode", source, available)
            _link(process, "has_flowElements", individual, available)
            summary["relations"][relation] += 1

    out.save(file=str(out_file))
    summary["inverse_triples_added"] = _write_inverses(out_file)
    summary["classes"] = dict(summary["classes"])
    summary["relations"] = dict(summary["relations"])
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("extraction", help="finder3 output (JSON or the printed dict)")
    ap.add_argument("-o", "--output", required=True, help="where to write the populated ontology")
    ap.add_argument("--ontology", default="BPMNbasedOntologyV1_2.owl", help="ontology to populate")
    args = ap.parse_args()
    summary = populate(load_extraction(args.extraction), args.ontology, args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"✅ Wrote {args.output}")


if __name__ == "__main__":
    main()
