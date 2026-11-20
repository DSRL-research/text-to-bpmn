"""Build the authored loan reference model, reference_authored.bpmn.

    python3 -m text2bpmn.cases.loan.build_reference

Written from the textbook process description in `input.txt` (paper Sec. 4.5)
and the reference task list recovered from the original evaluator. It is an
authored model, not an extracted one. See README.md for the one place it
differs from the recovered list.

It was the loan reference (reference.bpmn) of the release runs at
revision-final-3, whose saved scores are against it (comparison_authored.json
in each of the four loan folders, whose comparison.json is now the textbook
score). By
decision D12 the reference is now the textbook's Solution 3.2, built by
build_textbook_reference.py; this script writes the authored model to
reference_authored.bpmn and never to reference.bpmn.
"""
from pathlib import Path

from text2bpmn.bpmn_xml import to_xml
from text2bpmn.structure import Flow, Node, Process

TASKS = [("credit_history", "Check credit history", "Financial Officer"),
         ("loan_risk", "Assess loan risk", "System"),
         ("appraisal", "Appraise property", "Property Appraiser"),
         ("eligibility", "Assess eligibility", "Loan Officer"),
         ("reject", "Reject application", "Loan Officer"),
         ("acceptance_pack", "Prepare acceptance pack", "Loan Officer"),
         ("notify", "Notify application status", "Loan Officer")]
GATEWAYS = [("and_split", "parallelGateway", "", "Loan Officer"),
            ("and_join", "parallelGateway", "", "Loan Officer"),
            ("xor_split", "exclusiveGateway", "Applicant eligible?", "Loan Officer"),
            ("xor_join", "exclusiveGateway", "", "Loan Officer")]
FLOWS = [("start", "and_split", ""), ("and_split", "credit_history", ""),
         ("credit_history", "loan_risk", ""), ("loan_risk", "and_join", ""),
         ("and_split", "appraisal", ""), ("appraisal", "and_join", ""),
         ("and_join", "eligibility", ""), ("eligibility", "xor_split", ""),
         ("xor_split", "reject", "not eligible"), ("xor_split", "acceptance_pack", "eligible"),
         ("reject", "xor_join", ""), ("acceptance_pack", "xor_join", ""),
         ("xor_join", "notify", ""), ("notify", "end", "")]


def build():
    p = Process()
    p.nodes["start"] = Node("start", "startEvent", "Application received", "Loan Officer", "reference")
    for node_id, name, lane in TASKS:
        p.nodes[node_id] = Node(node_id, "task", name, lane, "reference")
    for node_id, kind, name, lane in GATEWAYS:
        p.nodes[node_id] = Node(node_id, kind, name, lane, "reference")
    p.nodes["end"] = Node("end", "endEvent", "Applicant notified", "Loan Officer", "reference")
    p.flows = [Flow(*f) for f in FLOWS]
    return p


if __name__ == "__main__":
    out = Path(__file__).parent / "reference_authored.bpmn"
    out.write_text(to_xml(build(), "Loan Application Eligibility Assessment"), encoding="utf-8")
    print(f"✅ Wrote {out}")
