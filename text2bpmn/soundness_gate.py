"""Whether a model is sound, by playing its token game; and the gate that keeps
every model relation idea 3 builds sound.

    python3 -m text2bpmn.soundness_gate MODEL.bpmn [...]   # the verdict for saved models

WOFLAN (text2bpmn/checks/soundness.py, through pm4py) is the external audit of
every generated model. It is not installed where the final runs are made, and
a run should not need it to keep its models sound, so the gate checks the same
property itself. A model is sound (classical soundness of a workflow net) when,
from the start,

1. **option to complete**: every reachable state can still reach the end;
2. **proper completion**: when the end is reached, no token is left anywhere;
3. **no dead elements**: every element fires in some run.

The states are the reachable markings of the model's token game, with BPMN's
semantics: an exclusive gateway passes one token from any incoming flow to one
outgoing flow of its choice, a parallel gateway waits for a token on every
incoming flow and puts one on every outgoing flow, a task or event fires for a
token on any incoming flow and puts one on each outgoing flow. The models the
pipeline builds are acyclic, so the markings are finite; past LIMIT of them
the verdict is "unknown", which the gate treats as unsound. On the 759 models
of the development repository's runs, `check` agrees with WOFLAN on 756. The
other 3, which WOFLAN rejects only because a place is not covered by an
S-component (a structural test), are sound by the definition: pm4py's own net
for each, explored marking by marking, is sound too (that repository's
text2bpmn/results/soundness_gate_agreement.md).

**The gate** (`decisions.build(..., gate=True)`, relation_mode decisions4): when
the model the relation stage built is not sound after the Validation Layer,
the construction is undone step by step, the riskiest first: the parallel
blocks, the last first, then the decisions' branches, the last first, until it
is. Every step is recorded in the process data as `soundness_gate`. With no
block and no branch left, the model is the text order, a sequence, and sound.
"""
import argparse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque

SINK = "__sink__"
LIMIT = 200_000
BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
KINDS = {"startEvent", "endEvent", "exclusiveGateway", "parallelGateway"}


def graph_of(process):
    """(nodes {id: kind}, flows [(id, source, target)]) of a structure.Process."""
    return ({n.id: n.kind for n in process.nodes.values()},
            [(f"Flow_{i + 1}", f.source, f.target) for i, f in enumerate(process.flows)])


def graph_of_bpmn(path):
    """The same from a BPMN 2.0 file; any activity counts as a task."""
    root = ET.parse(path).getroot()
    nodes, flows = {}, []
    for process in root.iter(f"{BPMN}process"):
        for child in process:
            tag = child.tag.replace(BPMN, "")
            if tag == "sequenceFlow":
                flows.append((child.get("id"), child.get("sourceRef"), child.get("targetRef")))
            elif tag in KINDS or tag.endswith("Task") or tag in ("task", "subProcess"):
                nodes[child.get("id")] = tag if tag in KINDS else "task"
    return nodes, flows


def _transitions(nodes, flows):
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for fid, s, t in flows:
        outgoing[s].append(fid)
        incoming[t].append(fid)
    out = []  # (node, consumed flows, produced flows)
    for n, kind in nodes.items():
        if kind == "startEvent":
            continue
        if kind == "parallelGateway":
            out.append((n, tuple(incoming[n]), tuple(outgoing[n])))
        elif kind == "exclusiveGateway":
            out += [(n, (i,), (o,)) for i in incoming[n] for o in (outgoing[n] or [None]) if o] + \
                   ([(n, (i,), ()) for i in incoming[n]] if not outgoing[n] else [])
        elif kind == "endEvent":
            out += [(n, (i,), (SINK,)) for i in incoming[n]]
        else:
            out += [(n, (i,), tuple(outgoing[n])) for i in incoming[n]]
    start = Counter(f for n, kind in nodes.items() if kind == "startEvent" for f in outgoing[n])
    return out, start


def check(nodes, flows, limit=LIMIT):
    """{"sound": True/False/None, "reason", "states"} for one model."""
    transitions, start = _transitions(nodes, flows)
    if not start:
        return {"sound": False, "reason": "no start event with an outgoing flow", "states": 0}
    key = lambda m: tuple(sorted((str(f), c) for f, c in m.items() if c))  # noqa: E731
    first = key(start)
    seen, edges, queue, fired = {first}, defaultdict(set), deque([first]), set()
    final = ((SINK, 1),)
    while queue:
        state = queue.popleft()
        marking = Counter(dict(state))
        if marking[SINK] and state != final:
            return {"sound": False, "reason": "no proper completion: the end is reached with tokens left",
                    "states": len(seen)}
        for node, consumed, produced in transitions:
            if all(marking[f] >= consumed.count(f) for f in consumed) and consumed:
                nxt = marking.copy()
                nxt.subtract(consumed)
                nxt.update(produced)
                after = key(nxt)
                fired.add(node)
                edges[after].add(state)
                if after not in seen:
                    if len(seen) >= limit:
                        return {"sound": None, "reason": f"more than {limit} states", "states": len(seen)}
                    seen.add(after)
                    queue.append(after)
    if final not in seen:
        return {"sound": False, "reason": "the end is never reached", "states": len(seen)}
    completes, stack = {final}, [final]
    while stack:
        for before in edges[stack.pop()]:
            if before not in completes:
                completes.add(before)
                stack.append(before)
    stuck = len(seen) - len(completes)
    if stuck:
        return {"sound": False, "reason": f"no option to complete from {stuck} reachable states (a deadlock)",
                "states": len(seen)}
    dead = sorted(n for n, kind in nodes.items() if kind != "startEvent" and n not in fired)
    if dead:
        return {"sound": False, "reason": f"dead elements: {dead[:5]}", "states": len(seen)}
    return {"sound": True, "reason": "", "states": len(seen)}


def verdict(data):
    """check() for finder3's process data, after the Validation Layer; a model the
    layer refuses is not sound either."""
    from text2bpmn.structure import validate
    try:
        process = validate(data)
    except ValueError as e:
        return {"sound": False, "reason": f"refused by the Validation Layer: {e}", "states": 0}
    return check(*graph_of(process))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("models", nargs="+")
    for path in ap.parse_args().models:
        v = check(*graph_of_bpmn(path))
        print(f"{'sound' if v['sound'] else 'unknown' if v['sound'] is None else 'UNSOUND'}\t{path}\t{v['reason']}")


if __name__ == "__main__":
    main()
