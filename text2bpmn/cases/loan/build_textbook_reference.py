"""Build the loan case reference model: the textbook's Solution 3.2.

    python3 -m text2bpmn.cases.loan.build_textbook_reference [-o OUT.bpmn]

Decision D12 of the revision, taken by the authors from the textbook before
any re-scoring: the loan reference is the solution to Exercise 3.2 in Dumas,
La Rosa, Mendling and Reijers, Fundamentals of Business Process Management,
2nd ed., Springer, 2018. It replaces the model authored from the description
(build_reference.py, now written to reference_authored.bpmn).

The model, with the textbook's labels verbatim:

- one pool and no lanes;
- start event "Loan application received";
- a parallel split into "Check credit history" -> "Assess loan risk" and, in
  parallel, "Appraise property", merged by a parallel join;
- "Assess eligibility", then an exclusive split: the flow "applicant not
  eligible" -> "Reject application" -> end event "Loan application rejected";
  the flow "applicant eligible" -> "Prepare acceptance pack" -> "Send
  acceptance pack" -> end event "Acceptance pack sent";
- no exclusive join: each outcome has its own end event. Gateways are unnamed.

The pool is named "Loan application" (decided by the authors with D12; the
authored reference's pool was "Loan Application Eligibility Assessment").

The file is BPMN 2.0 XML with diagram interchange: the pool and every node
have Bounds (tasks 100 x 80, gateways 50 x 50, events 36 x 36) on a grid of
columns, left to right, in three rows -- the upper branch of each split above
the centre line, the lower branch below it -- and every flow has orthogonal
waypoints. text2bpmn.render routes the lines itself; the waypoints are for
other tools (bpmn.io, Camunda Modeler).
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from text2bpmn import __version__

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
      "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
      "dc": "http://www.omg.org/spec/DD/20100524/DC",
      "di": "http://www.omg.org/spec/DD/20100524/DI"}
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)

POOL_NAME = "Loan application"
SIZE = {"task": (100, 80), "parallelGateway": (50, 50), "exclusiveGateway": (50, 50),
        "startEvent": (36, 36), "endEvent": (36, 36)}

# id, BPMN tag, name, column, row (-1 above the centre line, 0 on it, 1 below)
NODES = [("start", "startEvent", "Loan application received", 0, 0),
         ("and_split", "parallelGateway", "", 1, 0),
         ("credit_history", "task", "Check credit history", 2, -1),
         ("loan_risk", "task", "Assess loan risk", 3, -1),
         ("appraisal", "task", "Appraise property", 2, 1),
         ("and_join", "parallelGateway", "", 4, 0),
         ("eligibility", "task", "Assess eligibility", 5, 0),
         ("xor_split", "exclusiveGateway", "", 6, 0),
         ("reject", "task", "Reject application", 7, -1),
         ("end_rejected", "endEvent", "Loan application rejected", 8, -1),
         ("acceptance_pack", "task", "Prepare acceptance pack", 7, 1),
         ("send_pack", "task", "Send acceptance pack", 8, 1),
         ("end_sent", "endEvent", "Acceptance pack sent", 9, 1)]
# source, target, name
FLOWS = [("start", "and_split", ""),
         ("and_split", "credit_history", ""),
         ("credit_history", "loan_risk", ""),
         ("loan_risk", "and_join", ""),
         ("and_split", "appraisal", ""),
         ("appraisal", "and_join", ""),
         ("and_join", "eligibility", ""),
         ("eligibility", "xor_split", ""),
         ("xor_split", "reject", "applicant not eligible"),
         ("reject", "end_rejected", ""),
         ("xor_split", "acceptance_pack", "applicant eligible"),
         ("acceptance_pack", "send_pack", ""),
         ("send_pack", "end_sent", "")]

FIRST_CENTRE_X, COLUMN = 110, 160   # centre of column 0, and the distance between columns
CENTRE_Y, ROW = 240, 140            # the centre line, and the distance between rows
MARGIN = 60                         # free space inside the pool below and right of the outermost nodes


def bounds():
    """Each node's (x, y, width, height), centred on its column and row."""
    out = {}
    for node_id, tag, _, column, row in NODES:
        w, h = SIZE[tag]
        cx, cy = FIRST_CENTRE_X + column * COLUMN, CENTRE_Y + row * ROW
        out[node_id] = (cx - w / 2, cy - h / 2, w, h)
    return out


def pool_bounds(boxes):
    """The pool from (0, 0), its 30 px name strip left of column 0."""
    assert min(y for _, y, _, _ in boxes.values()) >= MARGIN
    assert min(x for x, _, _, _ in boxes.values()) >= 30 + MARGIN / 2
    right = max(x + w for x, _, w, _ in boxes.values()) + MARGIN
    bottom = max(y + h for _, y, _, h in boxes.values()) + MARGIN
    return 0, 0, right, bottom


def waypoints(source, target):
    """Orthogonal: straight along a row; out of a split's upper or lower tip
    and along the target's row; along the source's row into a join's tip."""
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    s_mid, t_mid = sy + sh / 2, ty + th / 2
    if s_mid == t_mid:
        return [(sx + sw, s_mid), (tx, t_mid)]
    if sh == 50 and sw == 50 and abs(s_mid - CENTRE_Y) < 1:     # leaving a gateway on the centre line
        tip = sy if t_mid < s_mid else sy + sh
        return [(sx + sw / 2, tip), (sx + sw / 2, t_mid), (tx, t_mid)]
    if th == 50 and tw == 50 and abs(t_mid - CENTRE_Y) < 1:     # entering a gateway on the centre line
        tip = ty if s_mid < t_mid else ty + th
        return [(sx + sw, s_mid), (tx + tw / 2, s_mid), (tx + tw / 2, tip)]
    mid = (sx + sw + tx) / 2
    return [(sx + sw, s_mid), (mid, s_mid), (mid, t_mid), (tx, t_mid)]


def _q(prefix, tag):
    return f"{{{NS[prefix]}}}{tag}"


def _num(value):
    return f"{value:g}"


def to_xml():
    flow_ids = [f"Flow_{i + 1}" for i in range(len(FLOWS))]
    defs = ET.Element(_q("bpmn", "definitions"), {
        "id": "Definitions_1", "targetNamespace": "http://bpmn.io/schema/bpmn",
        "exporter": "text2bpmn.cases.loan.build_textbook_reference", "exporterVersion": __version__})
    collaboration = ET.SubElement(defs, _q("bpmn", "collaboration"), {"id": "Collaboration_1"})
    ET.SubElement(collaboration, _q("bpmn", "participant"),
                  {"id": "Participant_1", "name": POOL_NAME, "processRef": "Process_1"})
    process = ET.SubElement(defs, _q("bpmn", "process"), {"id": "Process_1", "isExecutable": "false"})
    for node_id, tag, name, _, _ in NODES:
        incoming = [fid for fid, (_, t, _) in zip(flow_ids, FLOWS) if t == node_id]
        outgoing = [fid for fid, (s, _, _) in zip(flow_ids, FLOWS) if s == node_id]
        attrs = {"id": node_id}
        if name:
            attrs["name"] = name
        if tag.endswith("Gateway"):
            attrs["gatewayDirection"] = "Diverging" if len(outgoing) > 1 else "Converging"
        element = ET.SubElement(process, _q("bpmn", tag), attrs)
        for fid in incoming:
            ET.SubElement(element, _q("bpmn", "incoming")).text = fid
        for fid in outgoing:
            ET.SubElement(element, _q("bpmn", "outgoing")).text = fid
    for fid, (source, target, name) in zip(flow_ids, FLOWS):
        attrs = {"id": fid, "sourceRef": source, "targetRef": target}
        if name:
            attrs["name"] = name
        ET.SubElement(process, _q("bpmn", "sequenceFlow"), attrs)

    boxes = bounds()
    diagram = ET.SubElement(defs, _q("bpmndi", "BPMNDiagram"), {"id": "BPMNDiagram_1"})
    plane = ET.SubElement(diagram, _q("bpmndi", "BPMNPlane"),
                          {"id": "BPMNPlane_1", "bpmnElement": "Collaboration_1"})

    def shape(element_id, box, **extra):
        s = ET.SubElement(plane, _q("bpmndi", "BPMNShape"),
                          {"id": f"{element_id}_di", "bpmnElement": element_id, **extra})
        ET.SubElement(s, _q("dc", "Bounds"), {k: _num(v) for k, v in zip(("x", "y", "width", "height"), box)})

    shape("Participant_1", pool_bounds(boxes), isHorizontal="true")
    for node_id, tag, _, _, _ in NODES:
        shape(node_id, boxes[node_id], **({"isMarkerVisible": "true"} if tag == "exclusiveGateway" else {}))
    for fid, (source, target, _) in zip(flow_ids, FLOWS):
        edge = ET.SubElement(plane, _q("bpmndi", "BPMNEdge"), {"id": f"{fid}_di", "bpmnElement": fid})
        for x, y in waypoints(boxes[source], boxes[target]):
            ET.SubElement(edge, _q("di", "waypoint"), {"x": _num(x), "y": _num(y)})
    ET.indent(defs)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(defs, encoding="unicode") + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default=str(Path(__file__).parent / "reference.bpmn"))
    args = ap.parse_args()
    Path(args.out).write_text(to_xml(), encoding="utf-8")
    print(f"✅ Wrote {args.out}")


if __name__ == "__main__":
    main()
