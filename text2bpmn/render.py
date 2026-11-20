"""Draw a BPMN file as SVG: the stored node layout, with the flows routed again.

    python3 -m text2bpmn.render diagram.bpmn -o diagram.svg [--png diagram.png] [--dpi 300] [--pdf diagram.pdf]

Pools, lanes, tasks, gateways and events are drawn where the file's diagram
(BPMN DI) puts them. The sequence flows are routed here and the waypoints stored
in the file are not used: each flow is an orthogonal line that leaves its source
and enters its target at a side of the box, with the arrowhead at the target,
and that passes through no other task, gateway or event (it keeps CLEARANCE px
from every box). The route is a shortest path on a grid through the gaps
between boxes, with a cost for each bend, for crossing a line already drawn and
for running along one. Lines leave and enter at the middle of a side (the tips
of a diamond); a task also has ports a quarter of a side off the middle and on
the centre line of the other end (so that ends a fraction of a pixel apart in
the stored layout get a straight line), and a gateway with more than four flows
also uses the middles of the diamond's sides.
Flow names, and the names of gateways and events, are then put next to their
line or node where they cover no box, no other name and no line; a name with no
such place at 10 px is tried at 9 px. Nothing is random and ties go by document
order, so the same file always gives the same SVG.

Black on white and one font (Liberation Sans, which has the metrics of Arial and
Helvetica), so the SVG can go into a paper as it is. text2bpmn.render_check
measures a drawing: lines through boxes, labels that overlap. PNG conversion
shells out to inkscape or ImageMagick if either is installed.
"""
import argparse
import heapq
import shutil
import subprocess
import xml.etree.ElementTree as ET
from bisect import bisect_left, bisect_right
from pathlib import Path
from xml.sax.saxutils import escape

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
      "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
      "dc": "http://www.omg.org/spec/DD/20100524/DC",
      "di": "http://www.omg.org/spec/DD/20100524/DI"}

FONT_FAMILY = "Liberation Sans, Arial, Helvetica, sans-serif"
TASK_FONT, LABEL_FONT, LANE_FONT = 11, 10, 11   # px
LABEL_SIZES = (LABEL_FONT, LABEL_FONT - 1)      # the second only where no place is free
LINE_HEIGHT = 1.2                               # of the font size
ASCENT, DESCENT = 0.905, 0.212                  # Liberation Sans, of the font size
INK, PAPER = "#000000", "#ffffff"
HEADER = 30          # width of the name strip of a pool and of a lane
CLEARANCE = 10       # distance a line keeps from every box; also its end stub
TASK_PADDING = 5     # between a task's name and its border
LABEL_GAP = 4        # between a name and the line or node it belongs to
LABEL_PAD = 2        # free margin a placed name keeps around itself
NEAR_START = (6, 18, 30, 45)   # where a flow name is first tried, px along its line
ARROW = (8, 6)       # arrowhead length and width, px

# Routing costs, in px of line length.
BEND = 30            # per 90 degree turn
CROSS = 40           # per crossing of a line already routed
OVERLAP = 600        # per grid step along a line already routed
HUG = 0.6            # per px run at exactly CLEARANCE along a box
SIDE_COST = {"out": {"E": 0, "S": 8, "N": 8, "W": 40},
             "in": {"W": 0, "N": 8, "S": 8, "E": 40}}
OFF_CENTRE = 12      # for a task port a quarter of the side away from its middle
ALIGNED = 2          # for a task port on the centre line of the other end
PORT_REUSE = 1000    # for a port another line already uses

# Advance widths of Liberation Sans (1/1000 em), for characters 32..126, read
# from LiberationSans-Regular.ttf and -Bold.ttf with fontTools.
_WIDTHS = {
    False: [int(v) for v in (
        "278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,"
        "556,556,556,556,556,556,278,278,584,584,584,556,1015,667,667,722,722,667,611,778,"
        "722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,278,"
        "278,278,469,556,333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,"
        "556,556,333,500,278,556,500,722,500,500,500,334,260,334,584").split(",")],
    True: [int(v) for v in (
        "278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,556,556,556,556,"
        "556,556,556,556,556,556,333,333,584,584,584,611,975,722,722,722,722,667,611,778,"
        "722,278,556,722,611,833,722,778,667,778,722,667,611,722,667,944,667,667,611,333,"
        "278,333,584,556,333,556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,"
        "611,611,389,556,333,611,556,778,556,556,500,389,280,389,584").split(",")]}
_EXTRA_WIDTHS = {
    False: {"’": 222, "‘": 222, "“": 333, "”": 333, "–": 556, "—": 1000, "×": 584, "…": 1000,
            "é": 556, "è": 556, "á": 556, "à": 556, "ó": 556, "ö": 556, "ü": 556, "ä": 556,
            "ç": 500, "ñ": 556, "í": 278, "ú": 556, "°": 400, "·": 333},
    True: {"’": 278, "‘": 278, "“": 500, "”": 500, "–": 556, "—": 1000, "×": 584, "…": 1000,
           "é": 556, "è": 556, "á": 556, "à": 556, "ó": 611, "ö": 611, "ü": 611, "ä": 556,
           "ç": 556, "ñ": 611, "í": 278, "ú": 611, "°": 400, "·": 333}}

TASKS = {"task", "userTask", "serviceTask", "sendTask", "receiveTask", "manualTask",
         "businessRuleTask", "scriptTask", "subProcess", "callActivity", "transaction",
         "adHocSubProcess"}
MARKED_GATEWAYS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway"}
STEP = [(1, 0), (0, 1), (-1, 0), (0, -1)]      # grid directions 0 E, 1 S, 2 W, 3 N
DIR_INDEX = {"E": 0, "S": 1, "W": 2, "N": 3}


def text_width(text, size, bold=False):
    table, extra = _WIDTHS[bold], _EXTRA_WIDTHS[bold]
    return sum(table[ord(c) - 32] if 32 <= ord(c) <= 126 else extra.get(c, 556)
               for c in text) * size / 1000


def wrap(text, width, size, bold=False):
    """Greedy word wrap by measured width; line breaks in the name are kept. A
    word longer than the width gets a line of its own."""
    lines = []
    for paragraph in (text or "").replace("\r", "").split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if not line or text_width(candidate, size, bold) <= width:
                line = candidate
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines


def block_size(lines, size, bold=False):
    return (max((text_width(line, size, bold) for line in lines), default=0),
            len(lines) * size * LINE_HEIGHT)


def _text_lines(lines, cx, top, size, bold=False):
    """Lines centred on cx, the first line box starting at top (baselines explicit,
    so no renderer has to interpret dominant-baseline)."""
    lh = size * LINE_HEIGHT
    first = top + (lh - (ASCENT + DESCENT) * size) / 2 + ASCENT * size
    weight = " font-weight='bold'" if bold else ""
    return "".join(
        f"<text x='{cx:.2f}' y='{first + i * lh:.2f}' font-family='{FONT_FAMILY}' "
        f"font-size='{size}'{weight} text-anchor='middle' fill='{INK}'>{escape(line)}</text>"
        for i, line in enumerate(lines))


# --- geometry -----------------------------------------------------------------

def overlaps(a, b):
    """Open rectangles (x0, y0, x1, y1) share area."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def segment_hits(p, q, r):
    """An axis-parallel segment p-q passes through the open rectangle r."""
    (x1, y1), (x2, y2) = p, q
    if y1 == y2:
        return r[1] < y1 < r[3] and min(x1, x2) < r[2] and r[0] < max(x1, x2)
    if x1 == x2:
        return r[0] < x1 < r[2] and min(y1, y2) < r[3] and r[1] < max(y1, y2)
    raise ValueError("segment is not axis-parallel")


def grow(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


class Node:
    def __init__(self, element_id, kind, name, x, y, w, h, order):
        self.id, self.kind, self.name, self.order = element_id, kind, name, order
        self.box = (x, y, x + w, y + h)
        self.degree = 0      # number of sequence flows drawn at the node
        self.shape = ("task" if kind in TASKS else "gateway" if kind.endswith("Gateway")
                      else "event")

    def ports(self):
        """(direction, extra cost, point): the side midpoints (the tips of a
        diamond, the extremes of a circle); for a task also a quarter of the side
        off the middle; for a gateway also the middles of the diamond's four
        sides, left horizontally or vertically, for gateways with more than four
        flows."""
        x0, y0, x1, y1 = self.box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        qw, qh = (x1 - x0) / 4, (y1 - y0) / 4
        out = [("E", 0, (x1, cy)), ("W", 0, (x0, cy)), ("S", 0, (cx, y1)), ("N", 0, (cx, y0))]
        if self.shape == "task":
            for k in (-1, 1):
                out += [("E", OFF_CENTRE, (x1, cy + k * qh)), ("W", OFF_CENTRE, (x0, cy + k * qh)),
                        ("S", OFF_CENTRE, (cx + k * qw, y1)), ("N", OFF_CENTRE, (cx + k * qw, y0))]
        elif self.shape == "gateway" and self.degree > 4:
            for sx in (1, -1):
                for sy in (-1, 1):
                    point = (cx + sx * qw, cy + sy * qh)
                    out += [("E" if sx > 0 else "W", 2 * OFF_CENTRE, point),
                            ("S" if sy > 0 else "N", 2 * OFF_CENTRE, point)]
        return out

    def stub_end(self, side, point):
        """Where a line leaving point in that direction is CLEARANCE off the box."""
        x0, y0, x1, y1 = self.box
        return {"E": (x1 + CLEARANCE, point[1]), "W": (x0 - CLEARANCE, point[1]),
                "S": (point[0], y1 + CLEARANCE), "N": (point[0], y0 - CLEARANCE)}[side]


# --- reading the file ---------------------------------------------------------

class Diagram:
    def __init__(self, bpmn_path):
        root = ET.parse(bpmn_path).getroot()
        self.notes = []
        bpmn, di, dc = (f"{{{NS[k]}}}" for k in ("bpmn", "bpmndi", "dc"))
        elements = {}
        for element in root.iter():
            if element.get("id") and element.tag.startswith(bpmn):
                elements.setdefault(element.get("id"), element)
        order = {element_id: i for i, element_id in enumerate(elements)}

        diagrams = list(root.iter(f"{di}BPMNDiagram"))
        if len(diagrams) > 1:
            self.notes.append(f"{len(diagrams)} diagrams in the file; only the first is drawn")
        shapes = {}
        for shape in (diagrams[0].iter(f"{di}BPMNShape") if diagrams else []):
            bounds = shape.find(f"{dc}Bounds")
            if bounds is not None and shape.get("bpmnElement") in elements:
                shapes[shape.get("bpmnElement")] = (
                    tuple(float(bounds.get(k)) for k in ("x", "y", "width", "height")),
                    shape.get("isHorizontal"))
        if diagrams and any(True for _ in diagrams[0].iter(f"{di}BPMNLabel")):
            self.notes.append("label positions stored in the file (BPMNLabel) are not used; "
                              "names are placed by the renderer")

        self.pools, self.lanes, self.nodes = [], [], []
        for element_id, element in elements.items():
            kind = element.tag[len(bpmn):]
            name = element.get("name") or ""
            if kind in ("participant", "lane"):
                if element_id not in shapes:
                    self.notes.append(f"{kind} {element_id} has no layout and is not drawn")
                    continue
                (x, y, w, h), horizontal = shapes[element_id]
                if horizontal == "false":
                    self.notes.append(f"{kind} {element_id} is vertical; drawn as horizontal")
                (self.pools if kind == "participant" else self.lanes).append(
                    (element_id, name, (x, y, x + w, y + h)))
            elif kind in TASKS or kind.endswith("Gateway") or kind.endswith("Event"):
                if element_id not in shapes:
                    self.notes.append(f"{kind} {element_id} ({name!r}) has no layout and is not drawn")
                    continue
                (x, y, w, h), _ = shapes[element_id]
                node = Node(element_id, kind, name, x, y, w, h, order[element_id])
                self.nodes.append(node)
                if kind in TASKS and kind != "task":
                    self.notes.append(f"{kind} {element_id} drawn as a plain task (no type marker)")
                if node.shape == "gateway" and kind not in MARKED_GATEWAYS:
                    self.notes.append(f"{kind} {element_id} drawn without its marker")
                if node.shape == "event" and any(c.tag.endswith("EventDefinition") for c in element):
                    self.notes.append(f"{kind} {element_id} drawn without its event-definition marker")
                if node.shape == "event" and kind not in ("startEvent", "endEvent"):
                    self.notes.append(f"{kind} {element_id} drawn as an intermediate event")
            elif kind in ("dataObjectReference", "dataStoreReference", "textAnnotation", "group",
                          "messageFlow", "association", "dataInputAssociation",
                          "dataOutputAssociation"):
                self.notes.append(f"{kind} {element_id} is not drawn (not supported)")

        by_id = {n.id: n for n in self.nodes}
        self.flows = []
        for element_id, element in elements.items():
            if element.tag != f"{bpmn}sequenceFlow":
                continue
            source, target = by_id.get(element.get("sourceRef")), by_id.get(element.get("targetRef"))
            if source is None or target is None:
                self.notes.append(f"sequenceFlow {element_id} is not drawn: its source or target "
                                  "is not drawn")
                continue
            self.flows.append((element_id, element.get("name") or "", source, target))
            source.degree += 1
            target.degree += 1

        boxes = [b for _, _, b in self.pools + self.lanes] + [n.box for n in self.nodes]
        self.extent = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                       max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else (0, 0, 200, 200)

        # Name strips (pool and lane headers) are kept free of lines and names.
        self.headers, inner = [], []
        for _, _, (x0, y0, x1, y1) in self.pools:
            inside = [b for _, _, b in self.lanes
                      if b[0] >= x0 - 1 and b[2] <= x1 + 1 and b[1] >= y0 - 1 and b[3] <= y1 + 1]
            strip_end = max([b[0] + HEADER for b in inside] or [x0 + HEADER])
            self.headers.append((x0, y0, strip_end, y1))
            inner.append((strip_end, y0, x1, y1))
        if inner:
            self.area = (min(b[0] for b in inner), min(b[1] for b in inner),
                         max(b[2] for b in inner), max(b[3] for b in inner))
        else:
            self.area = grow(self.extent, 40)
        # Lane separators: lines and names should not run along or across them.
        self.lane_lines = sorted({y for _, _, b in self.lanes for y in (b[1], b[3])
                                  if self.area[1] < y < self.area[3]})


# --- routing ------------------------------------------------------------------

class Router:
    """Shortest orthogonal paths on a grid whose lines are the box edges grown
    by CLEARANCE, the port coordinates, the lane separators and the middles
    between them."""

    def __init__(self, diagram):
        self.nodes = diagram.nodes
        ax0, ay0, ax1, ay1 = diagram.area
        inset = CLEARANCE / 2
        self.bounds = (ax0 + inset, ay0 + inset, ax1 - inset, ay1 - inset)
        self.boxes = {n.id: n.box for n in self.nodes}
        self.obstacles = [grow(n.box, CLEARANCE) for n in self.nodes] + list(diagram.headers)
        self.hugged = [grow(n.box, CLEARANCE) for n in self.nodes]

        bx0, by0, bx1, by1 = self.bounds
        xs, ys = {bx0, bx1}, {by0, by1} | set(diagram.lane_lines)
        for x0, y0, x1, y1 in self.obstacles:
            xs |= {x0, x1}
            ys |= {y0, y1}
        xs, ys = sorted(xs), sorted(ys)
        xs = set(xs) | {(a + b) / 2 for a, b in zip(xs, xs[1:])}
        ys = set(ys) | {(a + b) / 2 for a, b in zip(ys, ys[1:])}
        for n in self.nodes:
            for side, _, point in n.ports():
                ex, ey = n.stub_end(side, point)
                xs.add(ex)
                ys.add(ey)
        self.X = sorted({x for x in xs if bx0 <= x <= bx1})
        self.Y = sorted({y for y in ys if by0 <= y <= by1})
        nx, ny = len(self.X), len(self.Y)
        self.nx, self.ny = nx, ny

        # blocked[i*ny+j]: point strictly inside an obstacle; hblock/vblock: the
        # grid step to the right of / below the point crosses one.
        self.blocked = bytearray(nx * ny)
        self.hblock = bytearray(nx * ny)
        self.vblock = bytearray(nx * ny)
        self.hhug = bytearray(nx * ny)
        self.vhug = bytearray(nx * ny)
        X, Y = self.X, self.Y
        for x0, y0, x1, y1 in self.obstacles:
            i_in = range(bisect_right(X, x0), bisect_left(X, x1))
            j_in = range(bisect_right(Y, y0), bisect_left(Y, y1))
            i_seg = range(bisect_left(X, x0), bisect_left(X, x1))
            j_seg = range(bisect_left(Y, y0), bisect_left(Y, y1))
            for i in i_in:
                for j in j_in:
                    self.blocked[i * ny + j] = 1
            for i in i_seg:
                if i + 1 < nx and X[i + 1] <= x1:
                    for j in j_in:
                        self.hblock[i * ny + j] = 1
            for j in j_seg:
                if j + 1 < ny and Y[j + 1] <= y1:
                    for i in i_in:
                        self.vblock[i * ny + j] = 1
        for y in diagram.lane_lines:   # never run along a lane separator
            j = bisect_left(Y, y)
            if j < ny and Y[j] == y:
                for i in range(nx):
                    self.hblock[i * ny + j] = 1
        for x0, y0, x1, y1 in self.hugged:
            for j in (bisect_left(Y, y0), bisect_left(Y, y1)):
                if j < ny and Y[j] in (y0, y1):
                    for i in range(bisect_left(X, x0), bisect_left(X, x1)):
                        self.hhug[i * ny + j] = 1
            for i in (bisect_left(X, x0), bisect_left(X, x1)):
                if i < nx and X[i] in (x0, x1):
                    for j in range(bisect_left(Y, y0), bisect_left(Y, y1)):
                        self.vhug[i * ny + j] = 1
        for j in (0, ny - 1):          # the pool border counts as a box side
            for i in range(nx):
                self.hhug[i * ny + j] = 1
        for i in (0, nx - 1):
            for j in range(ny):
                self.vhug[i * ny + j] = 1

        # what earlier routes occupy, as counts
        self.h_used = [0] * (nx * ny)   # grid step to the right of the point
        self.v_used = [0] * (nx * ny)   # grid step below the point
        self.pass_h = [0] * (nx * ny)   # a route passes the point horizontally
        self.pass_v = [0] * (nx * ny)
        self.port_used = {}
        self.routes = {}

    def _index(self, x, y):
        i, j = bisect_left(self.X, x), bisect_left(self.Y, y)
        if i < self.nx and j < self.ny and self.X[i] == x and self.Y[j] == y:
            return i * self.ny + j
        return None

    def _stubs(self, node, role, other):
        """Usable ports of a node: (cost, side, port key, port, stub end index).
        A task can also be joined on the other end's centre line, where that
        falls in the middle half of its side: a straight line where the stored
        layout has the two a fraction of a pixel apart."""
        out = []
        ports = node.ports()
        if node.shape == "task":
            x0, y0, x1, y1 = node.box
            ox, oy = (other.box[0] + other.box[2]) / 2, (other.box[1] + other.box[3]) / 2
            qw, qh = (x1 - x0) / 4, (y1 - y0) / 4
            taken = {point for _, _, point in ports}
            if y0 + qh <= oy <= y1 - qh:
                ports += [(side, ALIGNED, point) for side, point in (("E", (x1, oy)), ("W", (x0, oy)))
                          if point not in taken]
            if x0 + qw <= ox <= x1 - qw:
                ports += [(side, ALIGNED, point) for side, point in (("S", (ox, y1)), ("N", (ox, y0)))
                          if point not in taken]
        for side, extra, (px, py) in ports:
            end = node.stub_end(side, (px, py))
            gi = self._index(*end)
            if gi is None or self.blocked[gi]:
                continue
            if any(segment_hits((px, py), end, box) for nid, box in self.boxes.items()
                   if nid != node.id):
                continue
            key = (node.id, (px, py))
            cost = (abs(end[0] - px) + abs(end[1] - py) + SIDE_COST[role][side] + extra
                    + PORT_REUSE * self.port_used.get(key, 0))
            out.append((cost, side, key, (px, py), gi))
        return out

    def route(self, source, target):
        ny, X, Y = self.ny, self.X, self.Y
        starts, goals = self._stubs(source, "out", target), {}
        for cost, side, k, port, gi in self._stubs(target, "in", source):
            goals.setdefault(gi, []).append((cost, (DIR_INDEX[side] + 2) % 4, side, k, port))
        tx0, ty0, tx1, ty1 = grow(target.box, CLEARANCE)

        def h(gi):
            x, y = X[gi // ny], Y[gi % ny]
            return max(tx0 - x, 0, x - tx1) + max(ty0 - y, 0, y - ty1)

        heap, best, parent, seq, goal_count = [], {}, {}, 0, 0
        for cost, side, k, port, gi in starts:
            d = DIR_INDEX[side]
            key = gi * 4 + d
            if cost < best.get(key, float("inf")):
                best[key] = cost
                parent[key] = ("start", side, k, port)
                heapq.heappush(heap, (cost + h(gi), cost, seq, key))
                seq += 1
        done = None
        while heap:
            f, g, _, key = heapq.heappop(heap)
            if key < 0:                      # a finished route
                done = key
                break
            if g > best.get(key, float("inf")):
                continue
            gi, d = divmod(key, 4)
            for cost, inward, side, k, port in goals.get(gi, []):
                if d == (inward + 2) % 4:
                    continue                 # would have to turn back
                total = g + cost + (0 if d == inward else BEND)
                goal_count += 1
                goal_key = -goal_count
                parent[goal_key] = ("goal", key, side, k, port)
                best[goal_key] = total
                heapq.heappush(heap, (total, total, seq, goal_key))
                seq += 1
            i, j = divmod(gi, ny)
            for nd, (di, dj) in enumerate(STEP):
                if nd == (d + 2) % 4:
                    continue
                i2, j2 = i + di, j + dj
                if not (0 <= i2 < self.nx and 0 <= j2 < ny):
                    continue
                g2i = i2 * ny + j2
                if self.blocked[g2i]:
                    continue
                if dj == 0:
                    step = i * ny + j if di > 0 else g2i
                    if self.hblock[step]:
                        continue
                    length = abs(X[i2] - X[i])
                    extra = OVERLAP * (self.h_used[step] > 0) + HUG * length * self.hhug[step]
                    extra += CROSS * (self.pass_v[g2i] > 0)
                else:
                    step = i * ny + j if dj > 0 else g2i
                    if self.vblock[step]:
                        continue
                    length = abs(Y[j2] - Y[j])
                    extra = OVERLAP * (self.v_used[step] > 0) + HUG * length * self.vhug[step]
                    extra += CROSS * (self.pass_h[g2i] > 0)
                g2 = g + length + extra + (BEND if nd != d else 0)
                key2 = g2i * 4 + nd
                if g2 < best.get(key2, float("inf")):
                    best[key2] = g2
                    parent[key2] = ("step", key)
                    heapq.heappush(heap, (g2 + h(g2i), g2, seq, key2))
                    seq += 1
        if done is None:
            return None
        _, key, t_side, t_k, t_port = parent[done]
        cells = []
        while parent[key][0] == "step":
            cells.append(key // 4)
            key = parent[key][1]
        cells.append(key // 4)
        _, s_side, s_k, s_port = parent[key]
        cells.reverse()
        return {"cells": cells, "source_port": s_k, "target_port": t_k,
                "points": _simplify([s_port] + [(X[c // ny], Y[c % ny]) for c in cells] + [t_port])}

    def occupy(self, route, sign):
        ny = self.ny
        cells = route["cells"]
        for a, b in zip(cells, cells[1:]):
            if a // ny == b // ny:                       # same column: vertical step
                self.v_used[min(a, b)] += sign
                self.pass_v[a] += sign
                self.pass_v[b] += sign
            else:
                self.h_used[min(a, b)] += sign
                self.pass_h[a] += sign
                self.pass_h[b] += sign
        for port in (route["source_port"], route["target_port"]):
            self.port_used[port] = self.port_used.get(port, 0) + sign

    def route_all(self, flows, passes=2):
        """Shorter flows first (centre to centre, ties by document order); then
        every flow is taken up and routed again with all the others in place."""
        def centre(n):
            return ((n.box[0] + n.box[2]) / 2, (n.box[1] + n.box[3]) / 2)
        order = sorted(range(len(flows)), key=lambda i: (
            abs(centre(flows[i][2])[0] - centre(flows[i][3])[0])
            + abs(centre(flows[i][2])[1] - centre(flows[i][3])[1]), i))
        failed = set()
        for _ in range(passes):
            for i in order:
                flow_id, _, source, target = flows[i]
                if flow_id in self.routes:
                    self.occupy(self.routes.pop(flow_id), -1)
                route = self.route(source, target)
                if route is None:
                    failed.add(flow_id)
                    continue
                failed.discard(flow_id)
                self.routes[flow_id] = route
                self.occupy(route, +1)
        return failed


def _simplify(points):
    out = []
    for p in points:
        if out and p == out[-1]:
            continue
        if len(out) >= 2 and (out[-2][0] == out[-1][0] == p[0] or out[-2][1] == out[-1][1] == p[1]):
            out[-1] = p
        else:
            out.append(p)
    return out


def _fallback_route(source, target):
    """Straight orthogonal line, used only when no route exists (reported)."""
    s, t = source.box, target.box
    a, b = (s[2], (s[1] + s[3]) / 2), (t[0], (t[1] + t[3]) / 2)
    mid = (a[0] + b[0]) / 2
    return _simplify([a, (mid, a[1]), (mid, b[1]), b])


# --- names --------------------------------------------------------------------

class Placer:
    """Puts each name at the first candidate position that covers no box, no
    placed name, no line, no name strip and stays inside the drawing area; a
    position that crosses a lane separator only if nothing else is free."""

    def __init__(self, diagram, segments):
        self.node_boxes = [n.box for n in diagram.nodes]
        self.headers = diagram.headers
        self.area = diagram.area
        self.lane_lines = diagram.lane_lines
        self.segments = segments
        self.placed = []

    def cost(self, rect):
        r = grow(rect, LABEL_PAD)
        hard = sum(overlaps(r, b) for b in self.node_boxes)
        hard += sum(overlaps(r, b) for b in self.placed)
        hard += sum(overlaps(r, b) for b in self.headers)
        hard += sum(segment_hits(p, q, r) for p, q in self.segments)
        a = self.area
        hard += not (a[0] <= r[0] and r[2] <= a[2] and a[1] <= r[1] and r[3] <= a[3])
        soft = sum(r[1] < y < r[3] for y in self.lane_lines)
        return hard, soft

    def choose(self, candidates):
        """The best of candidates [(lines, (x, y, w, h))], in order of preference:
        (lines, rect, hard conflicts, soft conflicts). Not yet placed."""
        best = None
        for rank, (lines, (x, y, w, h)) in enumerate(candidates):
            rect = (x, y, x + w, y + h)
            hard, soft = self.cost(rect)
            if best is None or (hard, soft, rank) < best[0]:
                best = ((hard, soft, rank), lines, rect)
            if hard == 0 and soft == 0:
                break
        (hard, soft, _), lines, rect = best
        return lines, rect, hard, soft

    def place(self, make_candidates, sizes):
        """Try each font size in turn (the first is the normal one) until a
        position with no hard conflict is found; place the best."""
        best = None
        for size in sizes:
            lines, rect, hard, soft = self.choose(make_candidates(size))
            if best is None or (hard, soft) < best[1:3]:
                best = ((lines, rect, size), hard, soft)
            if hard == 0:
                break
        (lines, rect, size), hard, _ = best
        self.placed.append(rect)
        return lines, rect, size, hard


def _ordered(groups):
    """groups[w][p]: candidate p at wrap width w -> by position, then width."""
    return [group[p] for p in range(max(map(len, groups))) for group in groups if p < len(group)]


def _node_candidates(node, text, size):
    x0, y0, x1, y1 = node.box
    cx, cy, g = (x0 + x1) / 2, (y0 + y1) / 2, LABEL_GAP
    out = []
    for far in (0, 12, 24):
        groups = []
        for width in (110, 80, 150):
            lines = wrap(text, width, size)
            w, h = block_size(lines, size)
            positions = [
                (cx - w / 2, y0 - g - far - h), (cx - w / 2, y1 + g + far),
                (cx + 8 + far, y0 - g - h), (cx - 8 - far - w, y0 - g - h),
                (cx + 8 + far, y1 + g), (cx - 8 - far - w, y1 + g),
                (x1 + g + far, cy - 8 - h), (x0 - g - far - w, cy - 8 - h),
                (x1 + g + far, cy + 8), (x0 - g - far - w, cy + 8)]
            if node.shape != "gateway":       # events: below first
                positions[0], positions[1] = positions[1], positions[0]
            groups.append([(lines, (px, py, w, h)) for px, py in positions])
        out += _ordered(groups)
    return out


def _flow_candidates(points, text, size):
    """Beside each segment of the line, the segments nearest the source first."""
    out = []
    g = LABEL_GAP
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        groups = []
        for width in (100, 70, 140):
            lines = wrap(text, width, size)
            w, h = block_size(lines, size)
            spots = []
            if y1 == y2:
                lo, hi = min(x1, x2), max(x1, x2)
                alongs = [lo + d for d in NEAR_START] + [(lo + hi) / 2 - w / 2, hi - 6 - w]
                if x2 < x1:
                    alongs = [hi - d - w for d in NEAR_START] + [(lo + hi) / 2 - w / 2, lo + 6]
                alongs = [a for a in alongs if lo - w / 2 <= a <= hi - w / 2] or alongs[:1]
                for ax in alongs:
                    spots += [(ax, y1 - g - h), (ax, y1 + g)]
            else:
                lo, hi = min(y1, y2), max(y1, y2)
                alongs = [lo + d for d in NEAR_START] + [(lo + hi) / 2 - h / 2, hi - 6 - h]
                if y2 < y1:
                    alongs = [hi - d - h for d in NEAR_START] + [(lo + hi) / 2 - h / 2, lo + 6]
                alongs = [a for a in alongs if lo - h / 2 <= a <= hi - h / 2] or alongs[:1]
                for ay in alongs:
                    spots += [(x1 + g, ay), (x1 - g - w, ay)]
            groups.append([(lines, (sx, sy, w, h)) for sx, sy in spots])
        out += _ordered(groups)
    return out


def _task_lines(node):
    """The name inside the box: TASK_FONT, smaller only if a word or the line
    count does not fit."""
    x0, y0, x1, y1 = node.box
    width, height = x1 - x0 - 2 * TASK_PADDING, y1 - y0 - 2 * TASK_PADDING
    for size in (TASK_FONT, TASK_FONT - 1, TASK_FONT - 2):
        lines = wrap(node.name, width, size)
        w, h = block_size(lines, size)
        if w <= width and h <= height:
            return lines, size, True
    return lines, size, False


# --- drawing ------------------------------------------------------------------

def _attr(value):
    return escape(str(value), {'"': "&quot;"})


def layout(bpmn_path):
    """Everything the SVG shows, as data: nodes, routes, placed names, notes."""
    diagram = Diagram(bpmn_path)
    router = Router(diagram)
    failed = router.route_all(diagram.flows)
    routes = {}
    for flow_id, _, source, target in diagram.flows:
        if flow_id in failed or flow_id not in router.routes:
            routes[flow_id] = _fallback_route(source, target)
            diagram.notes.append(f"sequenceFlow {flow_id}: no route found, drawn straight")
        else:
            routes[flow_id] = router.routes[flow_id]["points"]
    segments = [s for pts in routes.values() for s in zip(pts, pts[1:])]
    placer = Placer(diagram, segments)

    labels = []   # (role, owner id, lines, size, bold, rect, rotated)
    for node in diagram.nodes:
        if node.shape == "task" and node.name:
            lines, size, fits = _task_lines(node)
            if size != TASK_FONT:
                diagram.notes.append(f"task {node.id}: name set at {size} px to fit its box")
            if not fits:
                diagram.notes.append(f"task {node.id}: name does not fit its box")
            w, h = block_size(lines, size)
            cx, cy = (node.box[0] + node.box[2]) / 2, (node.box[1] + node.box[3]) / 2
            labels.append(("task", node.id, lines, size, False, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), False))
    for node in diagram.nodes:
        if node.shape != "task" and node.name.strip():
            lines, rect, size, hard = placer.place(
                lambda size: _node_candidates(node, node.name, size), LABEL_SIZES)
            if size != LABEL_FONT:
                diagram.notes.append(f"{node.kind} {node.id}: name set at {size} px to find a free place")
            if hard:
                diagram.notes.append(f"{node.kind} {node.id}: no free place for its name")
            labels.append(("node", node.id, lines, size, False, rect, False))
    for flow_id, name, _, _ in diagram.flows:
        if name.strip():
            lines, rect, size, hard = placer.place(
                lambda size: _flow_candidates(routes[flow_id], name, size), LABEL_SIZES)
            if size != LABEL_FONT:
                diagram.notes.append(f"sequenceFlow {flow_id}: name set at {size} px to find a free place")
            if hard:
                diagram.notes.append(f"sequenceFlow {flow_id}: no free place for its name")
            labels.append(("flow", flow_id, lines, size, False, rect, False))
    for role, entries, bold in (("pool", diagram.pools, True), ("lane", diagram.lanes, False)):
        for element_id, name, (x0, y0, x1, y1) in entries:
            if name.strip():
                lines = wrap(name, y1 - y0 - 8, LANE_FONT, bold)
                w, h = block_size(lines, LANE_FONT, bold)
                if h > HEADER - 2:
                    diagram.notes.append(f"{role} {element_id}: name needs {len(lines)} lines "
                                         "in its name strip")
                cx, cy = x0 + HEADER / 2, (y0 + y1) / 2
                labels.append((role, element_id, lines, LANE_FONT, bold,
                               (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), True))
    return diagram, routes, labels


def render(bpmn_path):
    return render_with_notes(bpmn_path)[0]


def render_with_notes(bpmn_path):
    diagram, routes, labels = layout(bpmn_path)
    pad = 20
    ex0, ey0, ex1, ey1 = diagram.extent
    for *_, (lx0, ly0, lx1, ly1), rotated in labels:     # names may stand outside the pool
        if rotated:      # a pool or lane name, drawn turned by 90 degrees
            cx, cy, hw, hh = (lx0 + lx1) / 2, (ly0 + ly1) / 2, (lx1 - lx0) / 2, (ly1 - ly0) / 2
            lx0, ly0, lx1, ly1 = cx - hh, cy - hw, cx + hh, cy + hw
        ex0, ey0, ex1, ey1 = min(ex0, lx0), min(ey0, ly0), max(ex1, lx1), max(ey1, ly1)
    width, height = ex1 - ex0 + 2 * pad, ey1 - ey0 + 2 * pad
    al, aw = ARROW
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width:.2f}' height='{height:.2f}' "
           f"viewBox='0 0 {width:.2f} {height:.2f}'>",
           f"<defs><marker id='arrow' viewBox='0 0 {al} {aw}' refX='{al}' refY='{aw / 2:g}' "
           f"markerWidth='{al}' markerHeight='{aw}' markerUnits='userSpaceOnUse' orient='auto'>"
           f"<path d='M0,0 L{al},{aw / 2:g} L0,{aw} z' fill='{INK}'/></marker></defs>",
           f"<rect width='{width:.2f}' height='{height:.2f}' fill='{PAPER}'/>",
           f"<g id='drawing' transform='translate({pad - ex0:.2f},{pad - ey0:.2f})'>"]

    for role, entries, stroke in (("pool", diagram.pools, 1.2), ("lane", diagram.lanes, 0.8)):
        for element_id, _, (x0, y0, x1, y1) in entries:
            out.append(f"<rect data-kind='{role}' data-bpmn=\"{_attr(element_id)}\" x='{x0:.2f}' "
                       f"y='{y0:.2f}' width='{x1 - x0:.2f}' height='{y1 - y0:.2f}' fill='none' "
                       f"stroke='{INK}' stroke-width='{stroke}'/>")

    for flow_id, _, source, target in diagram.flows:
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in routes[flow_id])
        out.append(f"<polyline data-kind='flow' data-bpmn=\"{_attr(flow_id)}\" "
                   f"data-source=\"{_attr(source.id)}\" data-target=\"{_attr(target.id)}\" "
                   f"points='{points}' fill='none' stroke='{INK}' stroke-width='1.1' "
                   f"stroke-linejoin='miter' marker-end='url(#arrow)'/>")

    for node in diagram.nodes:
        x0, y0, x1, y1 = node.box
        w, h, cx, cy = x1 - x0, y1 - y0, (x0 + x1) / 2, (y0 + y1) / 2
        head = f"data-kind='{node.shape}' data-bpmn=\"{_attr(node.id)}\""
        if node.shape == "task":
            out.append(f"<rect {head} x='{x0:.2f}' y='{y0:.2f}' width='{w:.2f}' height='{h:.2f}' "
                       f"rx='8' fill='{PAPER}' stroke='{INK}' stroke-width='1.2'/>")
        elif node.shape == "gateway":
            out.append(f"<polygon {head} points='{cx:.2f},{y0:.2f} {x1:.2f},{cy:.2f} {cx:.2f},{y1:.2f} "
                       f"{x0:.2f},{cy:.2f}' fill='{PAPER}' stroke='{INK}' stroke-width='1.2'/>")
            if node.kind == "exclusiveGateway":
                d = w * 0.17
                out.append(f"<path d='M{cx - d:.2f},{cy - d:.2f} L{cx + d:.2f},{cy + d:.2f} "
                           f"M{cx + d:.2f},{cy - d:.2f} L{cx - d:.2f},{cy + d:.2f}' "
                           f"stroke='{INK}' stroke-width='3' fill='none'/>")
            elif node.kind == "parallelGateway":
                d = w * 0.24
                out.append(f"<path d='M{cx - d:.2f},{cy:.2f} L{cx + d:.2f},{cy:.2f} "
                           f"M{cx:.2f},{cy - d:.2f} L{cx:.2f},{cy + d:.2f}' "
                           f"stroke='{INK}' stroke-width='3' fill='none'/>")
            elif node.kind == "inclusiveGateway":
                out.append(f"<circle cx='{cx:.2f}' cy='{cy:.2f}' r='{w * 0.22:.2f}' fill='none' "
                           f"stroke='{INK}' stroke-width='2.4'/>")
        else:
            stroke = 3 if node.kind == "endEvent" else 1.4
            out.append(f"<circle {head} cx='{cx:.2f}' cy='{cy:.2f}' r='{w / 2:.2f}' fill='{PAPER}' "
                       f"stroke='{INK}' stroke-width='{stroke}'/>")
            if node.kind not in ("startEvent", "endEvent"):
                out.append(f"<circle cx='{cx:.2f}' cy='{cy:.2f}' r='{w / 2 - 3:.2f}' fill='none' "
                           f"stroke='{INK}' stroke-width='1'/>")

    for n, (role, owner, lines, size, bold, (x0, y0, x1, y1), rotated) in enumerate(labels):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        body = _text_lines(lines, cx, y0, size, bold)
        turn = f" transform='rotate(-90 {cx:.2f} {cy:.2f})'" if rotated else ""
        out.append(f"<g id='label-{n}' data-kind='label' data-role='{role}' "
                   f"data-for=\"{_attr(owner)}\"{turn}>{body}</g>")

    out.append("</g></svg>")
    return "\n".join(out), diagram.notes


def to_png(svg_path, png_path, dpi=300):
    if shutil.which("inkscape"):
        command = ["inkscape", str(svg_path), "--export-type=png", f"--export-filename={png_path}",
                   "-d", str(dpi), "--export-background=#ffffff", "--export-background-opacity=1"]
    elif shutil.which("convert"):
        command = ["convert", "-density", str(dpi), "-background", "white", str(svg_path), str(png_path)]
    else:
        raise RuntimeError("neither inkscape nor ImageMagick is installed; keep the SVG")
    subprocess.run(command, check=True, capture_output=True)


def to_pdf(svg_path, pdf_path):
    """Vector PDF of the SVG (inkscape), the text kept as text."""
    if not shutil.which("inkscape"):
        raise RuntimeError("inkscape is not installed; keep the SVG")
    subprocess.run(["inkscape", str(svg_path), "--export-type=pdf", f"--export-filename={pdf_path}"],
                   check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bpmn")
    ap.add_argument("-o", "--output", help="SVG file (default: alongside the input)")
    ap.add_argument("--png", help="also write a PNG here (needs inkscape or ImageMagick)")
    ap.add_argument("--dpi", type=int, default=300, help="PNG resolution (default 300)")
    ap.add_argument("--pdf", help="also write a vector PDF here (needs inkscape)")
    args = ap.parse_args()
    svg_path = Path(args.output or Path(args.bpmn).with_suffix(".svg"))
    svg, notes = render_with_notes(args.bpmn)
    svg_path.write_text(svg, encoding="utf-8")
    print(f"✅ Wrote {svg_path}")
    for note in dict.fromkeys(notes):
        print(f"   note: {note}")
    if args.png:
        to_png(svg_path, args.png, args.dpi)
        print(f"✅ Wrote {args.png}")
    if args.pdf:
        to_pdf(svg_path, args.pdf)
        print(f"✅ Wrote {args.pdf}")


if __name__ == "__main__":
    main()
