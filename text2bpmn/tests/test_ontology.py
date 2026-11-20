"""The ontology population: relations and actors reach the OWL file."""
import re
from pathlib import Path

import pytest

from text2bpmn.ontology import EXTRA_NAMESPACE, populate

REPO = Path(__file__).resolve().parents[2]
ONTOLOGY = REPO / "BPMNbasedOntologyV1_2.owl"

PROCESS = {
    "participants": ["The Clerk", "The Manager"],
    "elements": [
        {"id": "StartEvent_1", "name": "Start", "type": "startEvent", "lane": "The Clerk"},
        {"id": "Activity_a", "name": "Check the order", "type": "task", "lane": "The Clerk",
         "metadata": ["for large orders"]},
        {"id": "Gateway_x", "name": "If the order is urgent", "type": "exclusiveGateway",
         "lane": "The Manager"},
        {"id": "Activity_b", "name": "Ship the order", "type": "task", "lane": "The Manager"},
        {"id": "Activity_c", "name": "Cancel the order", "type": "task", "lane": "The Manager"},
        {"id": "EndEvent_1", "name": "End", "type": "endEvent", "lane": "The Manager"},
    ],
    "flows": [
        {"id": "Flow_1", "source": "StartEvent_1", "target": "Activity_a", "relation": "SEQUENCE"},
        {"id": "Flow_2", "source": "Activity_a", "target": "Gateway_x", "relation": "SEQUENCE"},
        {"id": "Flow_3", "source": "Gateway_x", "target": "Activity_b", "name": "Yes",
         "relation": "TRUE_BRANCH"},
        {"id": "Flow_4", "source": "Gateway_x", "target": "Activity_c", "name": "No",
         "relation": "FALSE_BRANCH"},
        {"id": "Flow_5", "source": "Activity_b", "target": "EndEvent_1", "relation": "SEQUENCE"},
    ],
}

pytestmark = pytest.mark.skipif(not ONTOLOGY.exists(), reason="ontology file not present")


@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    out = tmp_path_factory.mktemp("onto") / "out.owl"
    return populate(PROCESS, ONTOLOGY, out), out


def test_elements_become_individuals_of_their_bpmn_class(populated):
    """Two gateways, because the extraction goes through the Validation Layer
    first and it inserts the join where the branches converge."""
    summary, _ = populated
    assert summary["classes"] == {"StartEvent": 1, "Task": 3, "ExclusiveGateway": 2, "EndEvent": 1}


def test_each_flow_keeps_the_relation_it_came_from(populated):
    """Every edge used to become a bare SequenceFlow, so the branch relations
    were lost at the ontology boundary."""
    summary, _ = populated
    assert summary["relations"] == {"SEQUENCE": 5, "TRUE_BRANCH": 1, "FALSE_BRANCH": 1}


def test_the_relation_and_its_condition_are_queryable(populated):
    _, out = populated
    text = out.read_text(encoding="utf-8")
    assert "FalseBranchFlow" in text and "TrueBranchFlow" in text
    assert "extracted_relation" in text and "branch_condition" in text
    assert EXTRA_NAMESPACE.rstrip("#") in text, "added terms sit in their own namespace"


def test_actors_reach_the_ontology(populated):
    """Lanes were in the extraction and in the BPMN, but never in the OWL file."""
    summary, out = populated
    assert summary["lanes"] == {"Clerk": 2, "Manager": 5}
    assert "HumanResource" in out.read_text(encoding="utf-8")


def test_populating_twice_in_one_process_works(tmp_path):
    """Each run loads the ontology into a world of its own."""
    first = populate(PROCESS, ONTOLOGY, tmp_path / "a.owl")
    second = populate(PROCESS, ONTOLOGY, tmp_path / "b.owl")
    assert first["relations"] == second["relations"]


def test_the_ontology_and_the_diagram_name_the_same_actors(tmp_path):
    """Both come from the validated model, so they cannot disagree. Populated
    from the raw extraction, the ontology had "The Clerk" where the diagram had
    "Clerk", and an actor for the start event's default lane."""
    import rdflib
    from text2bpmn.bpmn_xml import to_xml
    from text2bpmn.structure import validate

    out = tmp_path / "out.owl"
    populate(PROCESS, ONTOLOGY, out)
    graph = rdflib.Graph()
    graph.parse(str(out))
    human_resource = rdflib.URIRef("http://BPMNbasedOntology#HumanResource")
    actors = sorted(str(label)
                    for individual in graph.subjects(rdflib.RDF.type, human_resource)
                    for label in graph.objects(individual, rdflib.RDFS.label))

    xml = to_xml(validate(PROCESS), "process")
    lanes = sorted(set(re.findall(r'<bpmn:lane[^>]*name="([^"]*)"', xml)))
    assert actors == lanes == ["Clerk", "Manager"]


def test_both_directions_of_every_inverse_pair_are_in_the_file(populated):
    """owlready2 saves one triple per inverse pair; the file now has both."""
    import rdflib
    from text2bpmn.ontology import BBO, INVERSE_PAIRS
    summary, out = populated
    graph = rdflib.Graph().parse(out)
    for forward, backward in INVERSE_PAIRS:
        p, q = rdflib.URIRef(BBO + forward), rdflib.URIRef(BBO + backward)
        pairs = set(graph.subject_objects(p))
        assert pairs, f"no {forward} triples at all"
        assert pairs == {(o, s) for s, o in graph.subject_objects(q)}, f"{forward} / {backward}"
    assert summary["inverse_triples_added"]["has_container"] == len(set(graph.subject_objects(
        rdflib.URIRef(BBO + "has_flowElements"))))


def test_the_population_conforms_to_bbo_shapes_with_rdfs_only(populated):
    """BBO's MinMaxShape_FlowElement requires has_container on every flow
    element; with only has_flowElements in the file, every one violated it
    under RDFS inference. Needs pyshacl and the fetched shapes
    (text2bpmn/checks/fetch_bbo.py)."""
    pytest.importorskip("pyshacl")
    import rdflib
    from pyshacl import validate
    shapes = REPO / "text2bpmn" / "checks" / "shacl" / "SHACLshapes.ttl"
    if not shapes.exists():
        pytest.skip("BBO shapes not fetched")
    _, out = populated
    conforms, _, text = validate(rdflib.Graph().parse(out), shacl_graph=rdflib.Graph().parse(shapes),
                                 ont_graph=rdflib.Graph().parse(ONTOLOGY), inference="rdfs")
    assert conforms, text


def test_a_model_can_be_populated_as_it_stands(tmp_path):
    """validate=False: no Validation Layer rule restructures the model, so a
    reference model's own gateways, including an inclusive one, are kept."""
    import rdflib
    model = {"elements": [dict(e) for e in PROCESS["elements"]], "flows": [dict(f) for f in PROCESS["flows"]]}
    model["elements"][2]["type"] = "inclusiveGateway"
    summary = populate(model, ONTOLOGY, tmp_path / "as_is.owl", validate=False)
    assert summary["classes"].get("InclusiveGateway") == 1
    assert "ExclusiveGateway" not in summary["classes"], "no join added, no type changed"
