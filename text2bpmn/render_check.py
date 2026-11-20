"""Measure a drawing made by text2bpmn.render, from the SVG alone.

    python3 -m text2bpmn.render_check figure.svg [more.svg ...] [--json out.json] [--metrics]

For each drawing:
  crossings     edge segments that pass through a task, gateway or event box
                that is not the edge's source or target
  own_box       edge segments that pass through the edge's own source or target
                box (anywhere but where the line starts or ends)
  bad_ends      edges that do not start on the outline of the source and end on
                the outline of the target, leaving and entering from outside (for
                a task: on a side, at right angles to it), with an arrowhead at
                the target; own_box and bad_ends use the drawn shapes (diamond,
                circle), crossings the boxes around them
  label_overlaps  label with label, label over a box (a task's name outside its
                own box counts), label crossed by a line
and, for information, names that cross a lane separator and flow names more than
10 px from their line.

The text boxes are what inkscape --query-all measures for the drawn glyphs; with
--metrics, or without inkscape, they are the line boxes from the font metrics
the renderer uses (larger than the glyphs, so stricter).
"""
import argparse
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from itertools import combinations

from text2bpmn.render import ASCENT, DESCENT, overlaps, segment_hits, text_width

SVG = "{http://www.w3.org/2000/svg}"
EPS = 0.5


def _points(text):
    return [tuple(float(v) for v in p.split(",")) for p in text.split()]


def _shape_box(element):
    tag = element.tag[len(SVG):]
    if tag == "rect":
        x, y = float(element.get("x")), float(element.get("y"))
        return (x, y, x + float(element.get("width")), y + float(element.get("height")))
    if tag == "polygon":
        pts = _points(element.get("points"))
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts), max(p[1] for p in pts))
    if tag == "circle":
        cx, cy, r = (float(element.get(k)) for k in ("cx", "cy", "r"))
        return (cx - r, cy - r, cx + r, cy + r)
    raise ValueError(tag)


def _metric_box(group):
    """Line boxes of a label group from the font metrics, rotation applied."""
    xs, ys = [], []
    for t in group.iter(f"{SVG}text"):
        size = float(t.get("font-size"))
        w = text_width(t.text or "", size, t.get("font-weight") == "bold")
        x, base = float(t.get("x")), float(t.get("y"))
        x0 = {"middle": x - w / 2, "end": x - w}.get(t.get("text-anchor"), x)
        xs += [x0, x0 + w]
        ys += [base - ASCENT * size, base + DESCENT * size]
    box = (min(xs), min(ys), max(xs), max(ys))
    turn = re.match(r"rotate\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)", group.get("transform") or "")
    if turn:
        angle, cx, cy = (float(v) for v in turn.groups())
        assert angle in (-90.0, 90.0, 270.0, -270.0)
        corners = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])]
        s = -1 if angle in (-90.0, 270.0) else 1
        moved = [(cx - s * (y - cy), cy + s * (x - cx)) for x, y in corners]
        box = (min(p[0] for p in moved), min(p[1] for p in moved),
               max(p[0] for p in moved), max(p[1] for p in moved))
    return box


def _inkscape_boxes(svg_path):
    out = subprocess.run(["inkscape", "--query-all", str(svg_path)], check=True,
                         capture_output=True, text=True).stdout
    boxes = {}
    for line in out.splitlines():
        parts = line.strip().split(",")
        if len(parts) == 5:
            x, y, w, h = (float(v) for v in parts[1:])
            boxes[parts[0]] = (x, y, x + w, y + h)
    return boxes


def _on_side(point, box):
    """The side of box the point lies on (not at a corner), or None."""
    x, y = point
    x0, y0, x1, y1 = box
    if abs(x - x1) <= EPS and y0 < y < y1:
        return "E"
    if abs(x - x0) <= EPS and y0 < y < y1:
        return "W"
    if abs(y - y1) <= EPS and x0 < x < x1:
        return "S"
    if abs(y - y0) <= EPS and x0 < x < x1:
        return "N"
    return None


def _outline_value(kind, box, point):
    """< 1 inside the drawn shape, 1 on its outline, > 1 outside: the diamond of
    a gateway and the circle of an event (for a task, its box)."""
    x0, y0, x1, y1 = box
    a, b = (x1 - x0) / 2, (y1 - y0) / 2
    dx, dy = abs(point[0] - (x0 + a)) / a, abs(point[1] - (y0 + b)) / b
    if kind == "gateway":
        return dx + dy
    if kind == "event":
        return (dx * dx + dy * dy) ** 0.5
    return max(dx, dy)


def _passes_inside(kind, box, p, q):
    """The segment p-q enters the inside of the drawn shape (touching its
    outline does not count). The nearest point of the segment to the centre is
    the centre clamped to the segment, for all three shapes."""
    if kind == "task":
        return segment_hits(p, q, grow_in(box))
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    near = (min(max(cx, min(p[0], q[0])), max(p[0], q[0])),
            min(max(cy, min(p[1], q[1])), max(p[1], q[1])))
    return _outline_value(kind, box, near) < 1 - 1e-6


def _end_ok(kind, box, end, inner):
    """end lies on the outline of the shape and the segment end-inner leaves it
    outward; for a task, on a side and at right angles to it."""
    if kind == "task":
        side = _on_side(end, box)
        return side is not None and _direction(end, inner) == side
    return abs(_outline_value(kind, box, end) - 1) < 1e-3 and _outline_value(kind, box, inner) > 1


def _direction(p, q):
    if p[1] == q[1]:
        return "E" if q[0] > p[0] else "W"
    if p[0] == q[0]:
        return "S" if q[1] > p[1] else "N"
    return None


def _distance(rect, p, q):
    """Distance from a rectangle to an axis-parallel segment (a flat rectangle)."""
    sx0, sx1 = sorted((p[0], q[0]))
    sy0, sy1 = sorted((p[1], q[1]))
    gx = max(0.0, rect[0] - sx1, sx0 - rect[2])
    gy = max(0.0, rect[1] - sy1, sy0 - rect[3])
    return (gx * gx + gy * gy) ** 0.5


def check(svg_path, use_inkscape=True):
    root = ET.parse(svg_path).getroot()
    drawing = next(g for g in root.iter(f"{SVG}g") if g.get("id") == "drawing")
    dx, dy = (float(v) for v in re.match(r"translate\(([-\d.]+),([-\d.]+)\)",
                                         drawing.get("transform")).groups())
    nodes, lanes, edges, labels = {}, [], [], []
    for element in drawing.iter():
        kind = element.get("data-kind")
        if kind in ("task", "gateway", "event"):
            nodes[element.get("data-bpmn")] = (kind, _shape_box(element))
        elif kind == "lane":
            lanes.append(_shape_box(element))
        elif kind == "flow":
            edges.append((element.get("data-bpmn"), element.get("data-source"),
                          element.get("data-target"), _points(element.get("points")),
                          element.get("marker-end")))
        elif kind == "label":
            labels.append(element)

    source = "metrics"
    if use_inkscape and shutil.which("inkscape"):
        measured = _inkscape_boxes(svg_path)
        source = "inkscape"
    label_boxes = []
    for group in labels:
        if source == "inkscape":
            x0, y0, x1, y1 = measured[group.get("id")]
            box = (x0 - dx, y0 - dy, x1 - dx, y1 - dy)
        else:
            box = _metric_box(group)
        label_boxes.append((group.get("id"), group.get("data-role"), group.get("data-for"), box))

    report = {"svg": str(svg_path), "text_boxes": source, "nodes": len(nodes), "edges": len(edges),
              "labels": len(label_boxes), "crossings": 0, "own_box": 0, "bad_ends": 0,
              "label_label": 0, "label_box": 0, "label_line": 0,
              "names_across_lane_lines": 0, "flow_names_far_from_line": 0, "details": []}
    note = report["details"].append

    for flow_id, src, tgt, pts, marker in edges:
        segs = list(zip(pts, pts[1:]))
        for p, q in segs:
            if _direction(p, q) is None:
                report["bad_ends"] += 1
                note(f"{flow_id}: segment {p}-{q} is not horizontal or vertical")
                continue
            hit = [nid for nid, (_, box) in nodes.items()
                   if nid not in (src, tgt) and segment_hits(p, q, grow_in(box))]
            if hit:
                report["crossings"] += 1
                note(f"{flow_id}: segment {p}-{q} crosses {', '.join(hit)}")
        for nid in dict.fromkeys((src, tgt)):
            kind, box = nodes[nid]
            if any(_passes_inside(kind, box, p, q) for p, q in segs):
                report["own_box"] += 1
                note(f"{flow_id}: passes through its own end {nid}")
        ok = (marker == "url(#arrow)" and _end_ok(*nodes[src], pts[0], pts[1])
              and _end_ok(*nodes[tgt], pts[-1], pts[-2]))
        if not ok:
            report["bad_ends"] += 1
            note(f"{flow_id}: does not leave/enter at a box side at right angles (or no arrowhead)")

    segments = [(fid, p, q) for fid, _, _, pts, _ in edges for p, q in zip(pts, pts[1:])]
    lane_lines = sorted({y for b in lanes for y in (b[1], b[3])})
    for (a_id, a_role, a_for, a), (b_id, b_role, b_for, b) in combinations(label_boxes, 2):
        if overlaps(a, b):
            report["label_label"] += 1
            note(f"labels overlap: {a_role} {a_for} / {b_role} {b_for}")
    for label_id, role, owner, box in label_boxes:
        for nid, (kind, nbox) in nodes.items():
            if role == "task" and nid == owner:
                if not (nbox[0] <= box[0] and box[2] <= nbox[2] and nbox[1] <= box[1] and box[3] <= nbox[3]):
                    report["label_box"] += 1
                    note(f"name of task {owner} is not inside its box")
            elif overlaps(box, nbox):
                report["label_box"] += 1
                note(f"{role} label of {owner} covers {kind} {nid}")
        crossed = sorted({fid for fid, p, q in segments if segment_hits(p, q, box)})
        if crossed:
            report["label_line"] += 1
            note(f"{role} label of {owner} is crossed by {', '.join(crossed)}")
        if role in ("node", "flow") and any(box[1] < y < box[3] for y in lane_lines):
            report["names_across_lane_lines"] += 1
            note(f"{role} label of {owner} crosses a lane separator")
        if role == "flow":
            own = [(p, q) for fid, p, q in segments if fid == owner]
            if min(_distance(box, p, q) for p, q in own) > 10:
                report["flow_names_far_from_line"] += 1
                note(f"name of flow {owner} is more than 10 px from its line")
    report["label_overlaps"] = report["label_label"] + report["label_box"] + report["label_line"]
    return report


def grow_in(box):
    """The open interior, shrunk a little so that touching a side is not crossing."""
    return (box[0] + EPS, box[1] + EPS, box[2] - EPS, box[3] - EPS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("svg", nargs="+")
    ap.add_argument("--json", help="write the full reports here")
    ap.add_argument("--metrics", action="store_true", help="font-metric text boxes, not inkscape")
    args = ap.parse_args()
    reports = [check(path, use_inkscape=not args.metrics) for path in args.svg]
    head = ("crossings", "own_box", "bad_ends", "label_overlaps", "label_label", "label_box",
            "label_line", "names_across_lane_lines", "flow_names_far_from_line")
    print("svg\t" + "\t".join(head) + "\ttext boxes")
    for r in reports:
        print(r["svg"] + "\t" + "\t".join(str(r[k]) for k in head) + "\t" + r["text_boxes"])
        for line in r["details"]:
            print("    " + line)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2)


if __name__ == "__main__":
    main()
