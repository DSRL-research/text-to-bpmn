"""The SPARQL competency questions (text2bpmn/checks/cq/) on small hand-made graphs."""
from pathlib import Path

import rdflib

CQ = Path(__file__).resolve().parents[1] / "checks" / "cq"
B = rdflib.Namespace("http://BPMNbasedOntology#")
P = rdflib.Namespace("http://text2bpmn.local/process#")


def graph(nodes, edges):
    """nodes: {name: BBO class}; edges: (source, target) sequence flows."""
    g = rdflib.Graph()
    for name, kind in nodes.items():
        g.add((P[name], rdflib.RDF.type, B[kind]))
        g.add((P[name], rdflib.RDFS.label, rdflib.Literal(name)))
    for i, (source, target) in enumerate(edges):
        flow = P[f"flow{i}"]
        g.add((flow, rdflib.RDF.type, B.SequenceFlow))
        g.add((flow, B.has_sourceRef, P[source]))
        g.add((flow, B.has_targetRef, P[target]))
        g.add((P[source], B.has_nextFlowNode, P[target]))
    return g


def cq3(g):
    return {frozenset((str(r.task_a), str(r.task_b))) for r in g.query((CQ / "cq3.rq").read_text())}


def test_tasks_after_the_parallel_join_are_not_parallel():
    """The loan shape: a parallel block, then a decision whose two outcomes are
    exclusive. Only tasks on different branches before the join are parallel."""
    g = graph({"split": "ParallelGateway", "A": "Task", "B": "Task", "C": "Task", "join": "ParallelGateway",
               "D": "Task", "xor": "ExclusiveGateway", "E": "Task", "F": "Task"},
              [("split", "A"), ("A", "B"), ("B", "join"), ("split", "C"), ("C", "join"),
               ("join", "D"), ("D", "xor"), ("xor", "E"), ("xor", "F")])
    assert cq3(g) == {frozenset("AC"), frozenset("BC")}


def test_a_block_closed_by_an_exclusive_gateway_ends_there_too():
    """Camunda's dispatch of goods merges its parallel branches at an exclusive
    gateway; what follows the merge is reached from both branches."""
    g = graph({"split": "ParallelGateway", "A": "Task", "C": "Task", "merge": "ExclusiveGateway",
               "xor": "ExclusiveGateway", "E": "Task", "F": "Task"},
              [("split", "A"), ("A", "merge"), ("split", "C"), ("C", "merge"),
               ("merge", "xor"), ("xor", "E"), ("xor", "F")])
    assert cq3(g) == {frozenset("AC")}


def test_a_nested_block_counts_for_both_splits():
    g = graph({"outer": "ParallelGateway", "inner": "ParallelGateway", "A": "Task", "B": "Task",
               "inner_join": "ParallelGateway", "C": "Task", "outer_join": "ParallelGateway"},
              [("outer", "inner"), ("inner", "A"), ("inner", "B"), ("A", "inner_join"), ("B", "inner_join"),
               ("inner_join", "outer_join"), ("outer", "C"), ("C", "outer_join")])
    assert cq3(g) == {frozenset("AB"), frozenset("AC"), frozenset("BC")}


def test_a_model_without_a_parallel_split_answers_nothing():
    g = graph({"A": "Task", "xor": "ExclusiveGateway", "E": "Task", "F": "Task"},
              [("A", "xor"), ("xor", "E"), ("xor", "F")])
    assert cq3(g) == set()


def test_a_question_about_participants_is_not_applicable_to_a_reference_without_any():
    from text2bpmn.checks.cq_compare import compare_question, fmt
    generated = {("loan officer", "assess"), ("financial officer", "check history")}
    for name in ("cq1", "cq5"):
        cell = compare_question(name, set(), generated, reference_participants=0)
        assert fmt(cell) == "n/a" and cell["generated"] == 2 and cell["precision"] is None
    # other questions, and references with participants, are scored as before
    assert fmt(compare_question("cq7", set(), {"assess"}, 0)) == "0/0/1 (P 0.00, R -)"
    assert fmt(compare_question("cq1", {("loan officer", "assess")}, generated, 1)) == "1/1/2 (P 0.50, R 1.00)"
