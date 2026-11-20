"""Convert BPMN diagrams drawn in draw.io (the paper's reference figures, and the
published generated figures) to BPMN 2.0 XML, one file per pool.

    python3 -m text2bpmn.cases.drawio_to_bpmn DIAGRAM.drawio --page 0 --pool 0 -o OUT.bpmn

The model is converted exactly as drawn: no validation rules are applied.
Pools are numbered top to bottom. Free-floating text cells are not attached to
anything and are reported as skipped.
"""
import argparse
import base64
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

from text2bpmn.bpmn_xml import to_xml
from text2bpmn.structure import Flow, Node, Process


def _style(cell):
    style = cell.get("style") or ""
    kv = dict(part.split("=", 1) for part in style.split(";") if "=" in part)
    kv["_first"] = style.split(";")[0] if "=" not in style.split(";")[0] else ""
    return kv


def _text(value):
    value = re.sub(r"<br\s*/?>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _kind(kv):
    shape = kv.get("shape", "")
    if shape == "mxgraph.bpmn.task2" or shape == "mxgraph.bpmn.task":
        return "task"
    if shape.startswith("mxgraph.bpmn.gateway"):
        return {"exclusive": "exclusiveGateway", "parallel": "parallelGateway"}.get(kv.get("gwType"), "exclusiveGateway")
    if shape == "mxgraph.bpmn.event":
        return "endEvent" if kv.get("outline") == "end" else "startEvent"
    return None


def pages(path):
    root = ET.parse(path).getroot()
    for diagram in root.iter("diagram"):
        model = diagram.find("mxGraphModel")
        if model is None:
            raw = zlib.decompress(base64.b64decode(diagram.text.strip()), -15)
            model = ET.fromstring(urllib.parse.unquote(raw.decode()))
        yield diagram.get("name"), model


def convert(model, pool_index):
    cells = {c.get("id"): c for c in model.iter("mxCell")}
    swimlanes = {i for i, c in cells.items() if c.get("vertex") == "1" and _style(c)["_first"] == "swimlane"}
    pools = sorted((i for i in swimlanes if cells[i].get("parent") not in swimlanes),
                   key=lambda i: float(cells[i].find("mxGeometry").get("y", 0)))
    pool = pools[pool_index]

    def lane_of(cell_id):
        chain = []
        while cell_id in cells:
            chain.append(cell_id)
            cell_id = cells[cell_id].get("parent")
        if pool not in chain:
            return None
        lanes = [i for i in chain if i in swimlanes and i != pool]
        return _text(cells[lanes[0]].get("value")) if lanes else _text(cells[pool].get("value"))

    p = Process()
    skipped = []
    for i, c in cells.items():
        if c.get("vertex") != "1" or i in swimlanes:
            continue
        lane = lane_of(i)
        if lane is None:
            continue
        kind = _kind(_style(c))
        if kind:
            p.nodes[f"n_{re.sub(r'[^A-Za-z0-9_]', '_', i)}"] = Node(
                f"n_{re.sub(r'[^A-Za-z0-9_]', '_', i)}", kind, _text(c.get("value")), lane, "drawio")
        elif cells.get(c.get("parent"), {}).get("edge") != "1" and _text(c.get("value")):
            skipped.append(_text(c.get("value")))
    labels = {}
    for c in cells.values():
        parent = cells.get(c.get("parent"))
        if c.get("vertex") == "1" and parent is not None and parent.get("edge") == "1":
            labels[parent.get("id")] = _text(c.get("value"))
    def origin(cell_id):  # absolute offset of a cell's coordinate system
        x = y = 0.0
        while cell_id in cells:
            g = cells[cell_id].find("mxGeometry")
            if g is not None and cells[cell_id].get("vertex") == "1":
                x += float(g.get("x", 0))
                y += float(g.get("y", 0))
            cell_id = cells[cell_id].get("parent")
        return x, y

    boxes = {}
    for node_id in p.nodes:
        cell = cells[node_id[2:]] if node_id[2:] in cells else next(
            c for i, c in cells.items() if f"n_{re.sub(r'[^A-Za-z0-9_]', '_', i)}" == node_id)
        g = cell.find("mxGeometry")
        ox, oy = origin(cell.get("parent"))
        boxes[node_id] = (ox + float(g.get("x", 0)), oy + float(g.get("y", 0)),
                          float(g.get("width", 0)), float(g.get("height", 0)))

    def snap(edge, end):
        """Node under a connector's loose end, or None."""
        point = edge.find(f"mxGeometry/mxPoint[@as='{end}Point']")
        if point is None:
            return None
        ox, oy = origin(edge.get("parent"))
        px, py = ox + float(point.get("x", 0)), oy + float(point.get("y", 0))

        def gap(b):
            dx = max(b[0] - px, 0, px - (b[0] + b[2]))
            dy = max(b[1] - py, 0, py - (b[1] + b[3]))
            return (dx * dx + dy * dy) ** 0.5

        best = min(boxes, key=lambda n: gap(boxes[n]))
        return best if gap(boxes[best]) <= 15 else None

    def node_id(cell_id):
        return f"n_{re.sub(r'[^A-Za-z0-9_]', '_', cell_id or '')}"

    dangling, snapped = 0, []
    for i, c in cells.items():
        if c.get("edge") != "1" or lane_of(i) is None:
            continue
        s, t = node_id(c.get("source")), node_id(c.get("target"))
        if s not in p.nodes:
            s = snap(c, "source")
            snapped.append(("source", i, s))
        if t not in p.nodes:
            t = snap(c, "target")
            snapped.append(("target", i, t))
        if s in p.nodes and t in p.nodes:
            p.flows.append(Flow(s, t, _text(c.get("value")) or labels.get(i, "")))
        else:
            dangling += 1
    snaps = [f"{end} of {i} -> {p.nodes[n].name or p.nodes[n].kind}" for end, i, n in snapped if n]
    return p, _text(cells[pool].get("value")), skipped, dangling, snaps


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("drawio")
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--pool", type=int, default=0)
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    name, model = list(pages(args.drawio))[args.page]
    p, pool_name, skipped, dangling, snaps = convert(model, args.pool)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(to_xml(p, pool_name))
    kinds = {k: sum(n.kind == k for n in p.nodes.values()) for k in sorted({n.kind for n in p.nodes.values()})}
    print(f"{args.output}: page {name!r}, pool {pool_name!r}: {kinds}, flows {len(p.flows)}, "
          f"lanes {sorted({n.lane for n in p.nodes.values()})}")
    print(f"  skipped free text: {skipped}")
    print(f"  loose connector ends snapped to the touching shape: {snaps}")
    print(f"  connectors still not joining two shapes (dropped): {dangling}")


if __name__ == "__main__":
    main()
