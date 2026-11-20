"""Validation Layer (paper Sec. 3.3): turn finder3's raw element/flow graph
into well-formed BPMN control flow before serialization.

Rules, applied in this order:

1. clean     XML-safe ids, whitespace and " - " artefacts removed from names,
             duplicate, self-loop and dangling flows dropped.
2. types     An Activity entity that finder3 promoted to a gateway, because a
             TRUE/FALSE_BRANCH relation starts at it, is kept as a task. Its
             branches leave through a split gateway added by rule 6.
3. metadata  TASK_INFO, Activity Data and Further Specification entities are
             activity metadata, not tasks (Sec. 4.1):
             their text is attached as documentation to the nearest preceding
             task and the node is bypassed.
4. connect   Every node is reachable from the start event and can reach the end
             event (sequential consistency).
5. gateways  A gateway with at most one incoming and one outgoing flow is not a
             decision: it is bypassed and its condition text labels the flow,
             until none is left (removing one can leave a neighbour with one).
             A gateway that both merges and splits is divided into a join
             followed by a split; the join's type is chosen as in rule 6.
             A gateway that only merges is a join, and takes that type too.
6. split/join  A non-gateway node with several outgoing flows gets a split
             gateway: exclusive if any flow carries a branch label, otherwise
             parallel. A node with several incoming flows gets a join gateway of
             the type of the split its branches part at, the nearest split they
             all descend from (branch completeness, parallel flow integrity).
7. lanes     Lane names that differ only by a leading article or possessive
             ("The patient" / "A patient") are merged; an event or gateway with
             no actor's lane takes a neighbouring task's; anything left without
             a lane goes into "Process".

Every change is recorded in Process.log so each run can report what the rules
did to the extractor's output. `problems` then checks the structural properties
the rules guarantee, and `validate` raises if any remain.
"""
import re
from dataclasses import dataclass, field

GATEWAYS = ("exclusiveGateway", "parallelGateway")
METADATA_ORIGINS = ("TASK_INFO", "Activity Data", "Further Specification")
ARTICLES = re.compile(r"^(the|a|an|their|his|her|its)\s+", re.I)


@dataclass
class Node:
    id: str
    kind: str  # task | exclusiveGateway | parallelGateway | startEvent | endEvent
    name: str = ""
    lane: str = ""
    origin: str = ""  # finder3 entity group taken from the id, or "inserted"
    documentation: list = field(default_factory=list)


@dataclass
class Flow:
    source: str
    target: str
    name: str = ""
    relation: str = "SEQUENCE"  # what the extractor read this edge from


class Process:
    def __init__(self):
        self.nodes = {}  # insertion order = document order
        self.flows = []
        self.log = []
        self._counter = 0

    def incoming(self, node_id):
        return [f for f in self.flows if f.target == node_id]

    def outgoing(self, node_id):
        return [f for f in self.flows if f.source == node_id]

    def start(self):
        return next(n for n in self.nodes.values() if n.kind == "startEvent")

    def end(self):
        return next(n for n in self.nodes.values() if n.kind == "endEvent")

    def add_flow(self, source, target, name="", relation="SEQUENCE"):
        if source == target:
            return
        for f in self.flows:
            if f.source == source and f.target == target:
                if name and not f.name:
                    f.name = name
                return
        self.flows.append(Flow(source, target, name, relation))

    def insert_node(self, kind, name, lane, before=None, after=None):
        """Add a gateway and route all incoming flows of `before`, or all
        outgoing flows of `after`, through it."""
        self._counter += 1
        role = "join" if before else "split"
        node = Node(f"Gateway_{role}_{self._counter}", kind, name, lane, "inserted")
        self.nodes[node.id] = node
        if before:
            for f in self.incoming(before):
                f.target = node.id
            self.flows.append(Flow(node.id, before))
        else:
            for f in self.outgoing(after):
                f.source = node.id
            self.flows.append(Flow(after, node.id))
        return node

    def bypass(self, node_id, label=None):
        """Remove a node, connecting each predecessor to each successor."""
        ins, outs = self.incoming(node_id), self.outgoing(node_id)
        self.flows = [f for f in self.flows if node_id not in (f.source, f.target)]
        del self.nodes[node_id]
        for i in ins:
            for o in outs:
                # the bypassed node's incoming edge is the one being extended, so
                # the relation it was read from is the one that survives
                self.add_flow(i.source, o.target,
                              label if label is not None else (i.name or o.name), i.relation)


def _origin(raw_id):
    if raw_id.startswith("StartEvent"):
        return "StartEvent"
    if raw_id.startswith("EndEvent"):
        return "EndEvent"
    m = re.match(r"(.+?)_(split_|join_)?[0-9a-f]{8}$", raw_id)
    return m.group(1) if m else raw_id


def _clean_name(name):
    name = re.sub(r"\s*-\s*", "-", name or "")
    return re.sub(r"\s+", " ", name).strip()


def _xml_id(raw_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", raw_id)
    return safe if re.match(r"[A-Za-z_]", safe) else f"_{safe}"


def build(extraction):
    """Rule 1: load finder3's elements and flows into a clean Process."""
    p = Process()
    ids = {}
    for e in extraction["elements"]:
        node = Node(_xml_id(e["id"]), e["type"], _clean_name(e.get("name")),
                    e.get("lane") or "", _origin(e["id"]),
                    documentation=[_clean_name(m) for m in e.get("metadata") or []])
        ids[e["id"]] = node.id
        p.nodes[node.id] = node
    dropped = 0
    for f in extraction["flows"]:
        s, t = ids.get(f["source"]), ids.get(f["target"])
        if s is None or t is None or s == t:
            dropped += 1
            continue
        before = len(p.flows)
        p.add_flow(s, t, (f.get("name") or "").strip(), f.get("relation") or "SEQUENCE")
        dropped += len(p.flows) == before
    if not any(n.kind == "startEvent" for n in p.nodes.values()):
        p.nodes = {"StartEvent_1": Node("StartEvent_1", "startEvent", "Start", origin="inserted"), **p.nodes}
    if not any(n.kind == "endEvent" for n in p.nodes.values()):
        p.nodes["EndEvent_1"] = Node("EndEvent_1", "endEvent", "End", origin="inserted")
    p.log.append(("clean", f"{dropped} duplicate, self-loop or dangling flows dropped"))
    return p


def attach_metadata(p):
    """Rule 3: TASK_INFO nodes become documentation of the nearest preceding task."""
    for node in [n for n in p.nodes.values() if n.origin in METADATA_ORIGINS]:
        owner = _nearest_task(p, node.id, backwards=True) or _nearest_task(p, node.id, backwards=False)
        if owner and node.name:
            p.nodes[owner].documentation.append(node.name)
        p.bypass(node.id)
        p.log.append(("metadata", f"{node.name!r} -> documentation of "
                                   f"{p.nodes[owner].name if owner else 'nothing'!r}"))


def _nearest_task(p, node_id, backwards):
    seen, frontier = {node_id}, [node_id]
    while frontier:
        nxt = []
        for n in frontier:
            flows = p.incoming(n) if backwards else p.outgoing(n)
            for f in flows:
                m = f.source if backwards else f.target
                if m in seen:
                    continue
                seen.add(m)
                if p.nodes[m].kind == "task" and p.nodes[m].origin not in METADATA_ORIGINS:
                    return m
                nxt.append(m)
        frontier = nxt
    return None


def fix_types(p):
    """Rule 2: activities promoted to gateways stay tasks."""
    for node in p.nodes.values():
        if node.origin == "Activity" and node.kind in GATEWAYS:
            node.kind = "task"
            p.log.append(("types", f"{node.name!r}: {node.origin} typed as gateway -> task"))


def connect(p):
    """Rule 4: reachable from start, can reach end."""
    order = list(p.nodes)
    start, end = p.start().id, p.end().id

    def reach(src, forward):
        seen, stack = {src}, [src]
        while stack:
            n = stack.pop()
            for f in (p.outgoing(n) if forward else p.incoming(n)):
                m = f.target if forward else f.source
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        return seen

    reached = reach(start, True)
    for i, n in enumerate(order):
        if n not in reached:
            src = next((m for m in reversed(order[:i]) if m in reached and m != end), start)
            p.add_flow(src, n)
            reached |= reach(n, True)
            p.log.append(("connect", f"{p.nodes[n].name!r} unreachable -> linked from {p.nodes[src].name!r}"))
    finishing = reach(end, False)
    for i in range(len(order) - 1, -1, -1):
        n = order[i]
        if n not in finishing:
            dst = next((m for m in order[i + 1:] if m in finishing and m != start), end)
            p.add_flow(n, dst)
            finishing |= reach(n, False)
            p.log.append(("connect", f"{p.nodes[n].name!r} cannot reach end -> linked to {p.nodes[dst].name!r}"))


def normalise_gateways(p):
    """Rule 5: drop pass-through gateways, divide mixed ones.

    Pass-through gateways are removed until none is left, before any mixed one
    is divided. Removing one can turn a neighbour into one: `bypass` reconnects
    through `add_flow`, which drops a self-loop and merges a flow that already
    exists, so a decision whose two outcomes meet again at the removed gateway
    keeps a single outgoing flow. A single pass in document order left such a
    decision behind whenever it came first, and validation then refused the
    model (PET doc-4.1 under Qwen3.5-27B, 2026-11-09). Removing a gateway never
    adds a flow to another node, so the loop ends.
    """
    while True:
        passing = next((n for n in p.nodes.values() if n.kind in GATEWAYS
                        and len(p.incoming(n.id)) <= 1 and len(p.outgoing(n.id)) <= 1), None)
        if passing is None:
            break
        outs = p.outgoing(passing.id)
        label = passing.name or (outs[0].name if outs else "")
        p.bypass(passing.id, label=label)
        p.log.append(("gateways", f"pass-through gateway {passing.name!r} removed"))
    for node in [n for n in p.nodes.values() if n.kind in GATEWAYS]:
        ins, outs = p.incoming(node.id), p.outgoing(node.id)
        if len(ins) >= 2 and len(outs) >= 2:
            # the join takes the type of the split its branches come from, as
            # in rule 6, not the gateway's own: both outcomes of a decision
            # entering a parallel split were merged by a parallel join, which
            # waits for the outcome not taken -- a deadlock
            kind = _join_kind(p, ins)
            p.insert_node(kind, "", node.lane, before=node.id)
            p.log.append(("gateways", f"mixed gateway {node.name!r} divided into {kind} join + split"))
        elif len(ins) >= 2 and _join_kind(p, ins) != node.kind:
            # a gateway that only merges is a join, typed the same way: two
            # parallel lines that met at a decision word left without branches
            # were merged by an exclusive gateway, which passes both tokens on
            # (the goods dispatch case under relation idea 3, 2026-11-12)
            kind = _join_kind(p, ins)
            p.log.append(("gateways", f"merging {node.kind} {node.name!r} -> {kind}, the type of the split "
                                       f"its branches part at"))
            node.kind = kind


def _join_kind(p, incoming):
    """The type of the split the incoming branches part at.

    That is the nearest split every incoming branch descends from, not the
    first split found on each branch: two outcomes of a decision that each
    contain a parallel block meet a parallel split first on both paths, and
    a join typed from those waited for both outcomes -- a deadlock. Parallel
    only if the split they part at is parallel; exclusive otherwise,
    including when no split is common to them all.
    """
    common = set.intersection(*(_ancestors(p, f.source) for f in incoming))
    splits = {n for n in common if _split_kind(p, n)}
    nearest = [n for n in splits if not any(n != m and n in _ancestors(p, m) for m in splits)]
    kinds = {_split_kind(p, n) for n in nearest}
    return "parallelGateway" if kinds == {"parallelGateway"} else "exclusiveGateway"


def _split_kind(p, node_id):
    """What split a node is, if any: a gateway with two or more outgoing flows,
    or a task or event with several, which rule 6 turns into the split it
    chooses there (exclusive if a flow is labelled, parallel otherwise)."""
    outs = p.outgoing(node_id)
    if len(outs) < 2:
        return None
    kind = p.nodes[node_id].kind
    if kind in GATEWAYS:
        return kind
    return "exclusiveGateway" if any(f.name for f in outs) else "parallelGateway"


def _ancestors(p, node_id):
    """node_id and every node it can be reached from."""
    seen, stack = {node_id}, [node_id]
    while stack:
        for f in p.incoming(stack.pop()):
            if f.source not in seen:
                seen.add(f.source)
                stack.append(f.source)
    return seen


def add_splits_and_joins(p):
    """Rule 6: no implicit splits or merges on tasks and events."""
    for node in [n for n in list(p.nodes.values()) if n.kind not in GATEWAYS]:
        outs = p.outgoing(node.id)
        if len(outs) >= 2:
            kind = "exclusiveGateway" if any(f.name for f in outs) else "parallelGateway"
            p.insert_node(kind, "", node.lane, after=node.id)
            p.log.append(("split/join", f"{kind} split added after {node.name!r}"))
    for node in [n for n in list(p.nodes.values()) if n.kind not in GATEWAYS]:
        ins = p.incoming(node.id)
        if len(ins) >= 2:
            kind = _join_kind(p, ins)
            p.insert_node(kind, "", node.lane, before=node.id)
            p.log.append(("split/join", f"{kind} join added before {node.name!r}"))


def assign_lanes(p):
    """Rule 7: merge lane-name variants ("The patient" / "A patient") and put
    events and gateways without an actor into the lane of a neighbouring task."""
    display, renamed = {}, {}
    for n in p.nodes.values():
        key = ARTICLES.sub("", n.lane).strip().lower()
        if key and key not in display:
            label = ARTICLES.sub("", n.lane).strip()
            display[key] = label[:1].upper() + label[1:]
        if n.lane and display.get(key, "") != n.lane:
            renamed[n.lane] = display.get(key, "")
        n.lane = display.get(key, "")
    for original, merged in renamed.items():
        p.log.append(("lanes", f"lane {original!r} -> {merged!r}"))
    task_lanes = {n.lane for n in p.nodes.values() if n.kind == "task"}
    for _ in range(len(p.nodes)):
        changed = False
        for n in p.nodes.values():
            if n.kind != "task" and n.lane not in task_lanes:
                near = [p.nodes[f.target].lane for f in p.outgoing(n.id)] + \
                       [p.nodes[f.source].lane for f in p.incoming(n.id)]
                lane = next((l for l in near if l in task_lanes), None)
                if lane:
                    p.log.append(("lanes", f"{n.name or n.kind!r} in {n.lane or 'no lane'!r}, "
                                           f"which holds no task -> {lane!r}"))
                    n.lane, changed = lane, True
        if not changed:
            break
    for n in p.nodes.values():
        if not n.lane:
            n.lane = "Process"
            p.log.append(("lanes", f"{n.name or n.kind!r} has no lane -> 'Process'"))


def problems(p):
    """Structural properties the rules guarantee; an empty list means well-formed."""
    found = []
    for n in p.nodes.values():
        ins, outs = len(p.incoming(n.id)), len(p.outgoing(n.id))
        if n.kind in GATEWAYS:
            if ins <= 1 and outs <= 1:
                found.append(f"pass-through gateway {n.id}")
        else:
            if outs > 1:
                found.append(f"implicit split at {n.id}")
            if ins > 1:
                found.append(f"implicit merge at {n.id}")
            if n.kind != "startEvent" and ins == 0:
                found.append(f"no incoming flow at {n.id}")
            if n.kind != "endEvent" and outs == 0:
                found.append(f"no outgoing flow at {n.id}")
    return found


def validate(extraction):
    p = build(extraction)
    fix_types(p)  # before metadata, so promoted activities can own TASK_INFO text
    attach_metadata(p)
    connect(p)
    normalise_gateways(p)
    add_splits_and_joins(p)
    assign_lanes(p)
    remaining = problems(p)
    if remaining:
        raise ValueError(f"Validation Layer left structural problems: {remaining}")
    return p
