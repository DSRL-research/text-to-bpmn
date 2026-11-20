"""Serialize a validated Process to BPMN 2.0 XML with diagram layout.

Layout is layered and deterministic: a node's column is its longest-path
distance from the start event (back edges ignored), its lane is its actor, and
nodes sharing a lane and column are stacked. The result opens directly in
bpmn.io or Camunda Modeler without manual arrangement.
"""
import xml.etree.ElementTree as ET

from text2bpmn import __version__

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

SIZE = {"task": (100, 80), "exclusiveGateway": (50, 50), "parallelGateway": (50, 50),
        "startEvent": (36, 36), "endEvent": (36, 36)}
COL_W, ROW_H = 150, 120
POOL_HEADER, LANE_HEADER = 30, 30


def _q(prefix, tag):
    return f"{{{NS[prefix]}}}{tag}"


def columns(p):
    """Longest-path column per node over the graph without back edges."""
    succ = {n: [f.target for f in p.outgoing(n)] for n in p.nodes}
    order, state, back = [], {}, set()

    def dfs(n):
        state[n] = "open"
        for m in succ[n]:
            if state.get(m) == "open":
                back.add((n, m))
            elif m not in state:
                dfs(m)
        state[n] = "done"
        order.append(n)

    for n in [p.start().id] + list(p.nodes):
        if n not in state:
            dfs(n)
    col = {n: 0 for n in p.nodes}
    for n in reversed(order):  # reverse post-order is a topological order
        for m in succ[n]:
            if (n, m) not in back:
                col[m] = max(col[m], col[n] + 1)
    return col, back


def layout(p):
    col, back = columns(p)
    lanes = list(dict.fromkeys(n.lane for n in p.nodes.values()))
    rows = {}
    slot = {}
    for n in sorted(p.nodes, key=lambda n: (col[n], list(p.nodes).index(n))):
        key = (p.nodes[n].lane, col[n])
        slot[n] = rows.get(key, 0)
        rows[key] = slot[n] + 1
    lane_rows = {l: max([r for (ln, _), r in rows.items() if ln == l] or [1]) for l in lanes}
    lane_top, y = {}, 0
    for l in lanes:
        lane_top[l] = y
        y += lane_rows[l] * ROW_H
    left = POOL_HEADER + LANE_HEADER + 20
    bounds = {}
    for n, node in p.nodes.items():
        w, h = SIZE[node.kind]
        bounds[n] = (left + col[n] * COL_W + (COL_W - w) / 2,
                     lane_top[node.lane] + slot[n] * ROW_H + (ROW_H - h) / 2, w, h)
    width = left + (max(col.values()) + 1) * COL_W + 20
    lane_bounds = {l: (POOL_HEADER, lane_top[l], width - POOL_HEADER, lane_rows[l] * ROW_H) for l in lanes}
    return bounds, lane_bounds, (0, 0, width, y), back


def waypoints(src, tgt, is_back, bottom):
    sx, sy, sw, sh = src
    tx, ty, tw, th = tgt
    if is_back:
        low = bottom - 10
        return [(sx + sw / 2, sy + sh), (sx + sw / 2, low), (tx + tw / 2, low), (tx + tw / 2, ty + th)]
    a, b = (sx + sw, sy + sh / 2), (tx, ty + th / 2)
    if a[1] == b[1]:
        return [a, b]
    mid = (a[0] + b[0]) / 2
    return [a, (mid, a[1]), (mid, b[1]), b]


def to_xml(p, name="Generated process"):
    flow_ids = {id(f): f"Flow_{i + 1}" for i, f in enumerate(p.flows)}
    defs = ET.Element(_q("bpmn", "definitions"), {
        "id": "Definitions_1", "targetNamespace": "http://bpmn.io/schema/bpmn",
        "exporter": "text2bpmn", "exporterVersion": __version__})
    collab = ET.SubElement(defs, _q("bpmn", "collaboration"), {"id": "Collaboration_1"})
    ET.SubElement(collab, _q("bpmn", "participant"),
                  {"id": "Participant_1", "name": name, "processRef": "Process_1"})
    proc = ET.SubElement(defs, _q("bpmn", "process"), {"id": "Process_1", "isExecutable": "false"})

    lanes = list(dict.fromkeys(n.lane for n in p.nodes.values()))
    lane_ids = {l: f"Lane_{i + 1}" for i, l in enumerate(lanes)}
    lane_set = ET.SubElement(proc, _q("bpmn", "laneSet"), {"id": "LaneSet_1"})
    for l in lanes:
        lane = ET.SubElement(lane_set, _q("bpmn", "lane"), {"id": lane_ids[l], "name": l})
        for n in p.nodes.values():
            if n.lane == l:
                ET.SubElement(lane, _q("bpmn", "flowNodeRef")).text = n.id

    for n in p.nodes.values():
        ins, outs = p.incoming(n.id), p.outgoing(n.id)
        attrs = {"id": n.id, "name": n.name}
        if n.kind in ("exclusiveGateway", "parallelGateway"):
            attrs["gatewayDirection"] = ("Mixed" if len(ins) > 1 and len(outs) > 1 else
                                         "Diverging" if len(outs) > 1 else
                                         "Converging" if len(ins) > 1 else "Unspecified")
        el = ET.SubElement(proc, _q("bpmn", n.kind), attrs)
        if n.documentation:
            ET.SubElement(el, _q("bpmn", "documentation")).text = "; ".join(n.documentation)
        for f in ins:
            ET.SubElement(el, _q("bpmn", "incoming")).text = flow_ids[id(f)]
        for f in outs:
            ET.SubElement(el, _q("bpmn", "outgoing")).text = flow_ids[id(f)]
    for f in p.flows:
        attrs = {"id": flow_ids[id(f)], "sourceRef": f.source, "targetRef": f.target}
        if f.name:
            attrs["name"] = f.name
        ET.SubElement(proc, _q("bpmn", "sequenceFlow"), attrs)

    bounds, lane_bounds, pool, back = layout(p)
    diagram = ET.SubElement(defs, _q("bpmndi", "BPMNDiagram"), {"id": "BPMNDiagram_1"})
    plane = ET.SubElement(diagram, _q("bpmndi", "BPMNPlane"),
                          {"id": "BPMNPlane_1", "bpmnElement": "Collaboration_1"})

    def shape(element_id, box, **extra):
        s = ET.SubElement(plane, _q("bpmndi", "BPMNShape"),
                          {"id": f"{element_id}_di", "bpmnElement": element_id, **extra})
        ET.SubElement(s, _q("dc", "Bounds"), {k: f"{v:g}" for k, v in zip("x y width height".split(), box)})

    shape("Participant_1", pool, isHorizontal="true")
    for l in lanes:
        shape(lane_ids[l], lane_bounds[l], isHorizontal="true")
    for n in p.nodes.values():
        extra = {"isMarkerVisible": "true"} if n.kind == "exclusiveGateway" else {}
        shape(n.id, bounds[n.id], **extra)
    for f in p.flows:
        e = ET.SubElement(plane, _q("bpmndi", "BPMNEdge"),
                          {"id": f"{flow_ids[id(f)]}_di", "bpmnElement": flow_ids[id(f)]})
        pts = waypoints(bounds[f.source], bounds[f.target], (f.source, f.target) in back, pool[3])
        for x, y in pts:
            ET.SubElement(e, _q("di", "waypoint"), {"x": f"{x:g}", "y": f"{y:g}"})

    ET.indent(defs)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(defs, encoding="unicode") + "\n"
