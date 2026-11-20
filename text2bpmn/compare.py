"""Compare a generated BPMN model with a reference model (ticket C10).

    python3 -m text2bpmn.compare --reference ref.bpmn --generated gen.bpmn [--json out.json]

Both models are read from BPMN XML, so nothing is typed in by hand. What this
does differently from the evaluator that produced the submitted version's
tables (kept in the development repository, not here):

- tasks are matched one-to-one by an optimal assignment on label similarity,
  above a threshold, so a merged or split task costs a false positive or
  negative instead of being free;
- edges are the task-to-task succession relation read off the model (following
  gateways and events), not a hand-typed list;
- GED follows the paper's definition: the cost of an edit path between the two
  full graphs. It is computed from an optimal node assignment, which makes it an
  upper bound on the true minimum, and it is reported as such.

Element counts (tasks, gateways, edges) are reported as TP/FP/FN with precision,
recall and F1, as in the paper's Tables 4-6.
"""
import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from scipy.optimize import linear_sum_assignment

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
TASK_TAGS = {"task", "userTask", "serviceTask", "manualTask", "scriptTask", "businessRuleTask",
             "sendTask", "receiveTask", "callActivity", "subProcess"}
GATEWAY_KIND = {"exclusiveGateway": "XOR", "parallelGateway": "AND", "inclusiveGateway": "OR",
                "eventBasedGateway": "EVENT", "complexGateway": "COMPLEX"}
ARTICLES = re.compile(r"\b(the|a|an|its|their|his|her)\b")
DEFAULT_THRESHOLD = 0.5


@dataclass
class Node:
    id: str
    kind: str  # "task", "gateway" or "event"
    name: str
    detail: str  # gateway kind, or the event tag
    role: str = ""  # split | join | mixed | plain


@dataclass
class Model:
    name: str
    nodes: dict = field(default_factory=dict)
    flows: list = field(default_factory=list)

    def of_kind(self, kind):
        return [n for n in self.nodes.values() if n.kind == kind]

    @property
    def tasks(self):
        return self.of_kind("task")

    @property
    def gateways(self):
        return self.of_kind("gateway")

    def successors(self, node_id):
        return [t for s, t in self.flows if s == node_id]

    def task_edges(self):
        """Task-to-task succession: a path that passes only gateways and events."""
        edges = set()
        for task in self.tasks:
            seen, frontier = set(), list(self.successors(task.id))
            while frontier:
                node_id = frontier.pop()
                if node_id in seen:
                    continue
                seen.add(node_id)
                node = self.nodes.get(node_id)
                if node is None:
                    continue
                if node.kind == "task":
                    edges.add((task.id, node_id))
                else:
                    frontier.extend(self.successors(node_id))
        return sorted(edges)

    def size(self):  # nodes and edges, as the paper's |G|
        return len(self.nodes) + len(self.flows)


def read_bpmn(path):
    import xml.etree.ElementTree as ET

    root = ET.parse(path).getroot()
    model = Model(name=Path(path).stem)
    incoming, outgoing = {}, {}
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        element_id = element.get("id")
        if not element_id:
            continue
        name = re.sub(r"\s+", " ", element.get("name") or "").strip()  # labels wrap across lines
        if tag in TASK_TAGS:
            model.nodes[element_id] = Node(element_id, "task", name, tag)
        elif tag in GATEWAY_KIND:
            model.nodes[element_id] = Node(element_id, "gateway", name, GATEWAY_KIND[tag])
        elif tag.endswith("Event") and not tag.endswith("EventDefinition"):
            model.nodes[element_id] = Node(element_id, "event", name, tag)
    for flow in root.iter(f"{{{BPMN}}}sequenceFlow"):
        source, target = flow.get("sourceRef"), flow.get("targetRef")
        if source in model.nodes and target in model.nodes:
            model.flows.append((source, target))
            outgoing[source] = outgoing.get(source, 0) + 1
            incoming[target] = incoming.get(target, 0) + 1
    for node in model.nodes.values():
        ins, outs = incoming.get(node.id, 0), outgoing.get(node.id, 0)
        node.role = ("mixed" if ins > 1 and outs > 1 else "split" if outs > 1
                     else "join" if ins > 1 else "plain")
    return model


def normalise(label):
    label = unicodedata.normalize("NFKD", (label or "").lower())
    label = re.sub(r"[^a-z0-9 ]", " ", label)
    return re.sub(r"\s+", " ", ARTICLES.sub(" ", label)).strip()


def similarity(a, b):
    """How close two labels are, in [0, 1].

    The largest of three views, so that neither wording nor word order alone
    decides: characters in sequence, the same with the words sorted (so
    "Check credit history" matches "Credit history check"), and word overlap
    after cutting each word to five characters (so "assess" meets
    "assessment").
    """
    a, b = normalise(a), normalise(b)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    sorted_ratio = SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio()
    stems_a, stems_b = {w[:5] for w in a.split()}, {w[:5] for w in b.split()}
    overlap = 2 * len(stems_a & stems_b) / (len(stems_a) + len(stems_b))
    return max(ratio, sorted_ratio, overlap)


def match_tasks(reference, generated, threshold=DEFAULT_THRESHOLD):
    """Optimal one-to-one assignment on label similarity, above the threshold."""
    ref, gen = reference.tasks, generated.tasks
    if not ref or not gen:
        return {}
    scores = [[similarity(r.name, g.name) for g in gen] for r in ref]
    rows, columns = linear_sum_assignment([[-s for s in row] for row in scores])
    return {ref[i].id: gen[j].id for i, j in zip(rows, columns) if scores[i][j] >= threshold}


def prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def gateway_counts(model):
    counts = {}
    for gateway in model.gateways:
        key = f"{gateway.detail}_{gateway.role}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def compare(reference, generated, threshold=DEFAULT_THRESHOLD):
    mapping = match_tasks(reference, generated, threshold)
    tasks = prf(len(mapping), len(generated.tasks) - len(mapping), len(reference.tasks) - len(mapping))

    ref_counts, gen_counts = gateway_counts(reference), gateway_counts(generated)
    tp = sum(min(ref_counts.get(k, 0), gen_counts.get(k, 0)) for k in set(ref_counts) | set(gen_counts))
    gateways = prf(tp, len(generated.gateways) - tp, len(reference.gateways) - tp)

    generated_edges = set(generated.task_edges())
    matched = {(s, t) for s, t in reference.task_edges()
               if (mapping.get(s), mapping.get(t)) in generated_edges}
    edges = prf(len(matched), len(generated_edges) - len(matched),
                len(reference.task_edges()) - len(matched))

    distance = graph_edit_distance(reference, generated, threshold)
    return {"tasks": tasks, "gateways": gateways, "edges": edges, "ged": distance,
            "mapping": [(reference.nodes[r].name, generated.nodes[g].name) for r, g in mapping.items()],
            "unmatched_reference": [t.name for t in reference.tasks if t.id not in mapping],
            "unmatched_generated": [t.name for t in generated.tasks if t.id not in set(mapping.values())]}


def substitution_cost(a, b, threshold):
    if a.kind != b.kind:
        return None  # never substitute across kinds; deleting and inserting is cheaper
    if a.kind == "task":
        score = similarity(a.name, b.name)
        return 1.0 if score < threshold else 1.0 - score
    if a.kind == "gateway":
        return 0.0 if (a.detail, a.role) == (b.detail, b.role) else (0.5 if a.detail == b.detail else 1.0)
    return 0.0 if a.detail == b.detail else 0.5


def graph_edit_distance(reference, generated, threshold=DEFAULT_THRESHOLD):
    """Cost of an edit path between the two graphs (paper Eqs. 11-12).

    The node mapping comes from an optimal assignment whose cost includes a
    local-structure term, then the returned distance is the true cost of that
    mapping's edit path. It is therefore an upper bound on the minimum.
    """
    ref_nodes, gen_nodes = list(reference.nodes.values()), list(generated.nodes.values())
    degree = lambda model, node_id: (sum(t == node_id for _, t in model.flows),
                                     sum(s == node_id for s, _ in model.flows))
    size = len(ref_nodes) + len(gen_nodes)
    cost = [[0.0] * size for _ in range(size)]
    for i, r in enumerate(ref_nodes):
        r_in, r_out = degree(reference, r.id)
        for j, g in enumerate(gen_nodes):
            g_in, g_out = degree(generated, g.id)
            substitution = substitution_cost(r, g, threshold)
            cost[i][j] = (1e6 if substitution is None else
                          substitution + 0.5 * abs(r_in - g_in) + 0.5 * abs(r_out - g_out))
        for j in range(len(gen_nodes), size):
            cost[i][j] = 1e6 if j - len(gen_nodes) != i else 1.0 + 0.5 * (r_in + r_out)
    for i in range(len(ref_nodes), size):
        for j, g in enumerate(gen_nodes):
            g_in, g_out = degree(generated, g.id)
            cost[i][j] = 1e6 if i - len(ref_nodes) != j else 1.0 + 0.5 * (g_in + g_out)
    rows, columns = linear_sum_assignment(cost)

    mapping, deleted, inserted = {}, [], []
    for i, j in zip(rows, columns):
        if i < len(ref_nodes) and j < len(gen_nodes):
            mapping[ref_nodes[i].id] = gen_nodes[j].id
        elif i < len(ref_nodes):
            deleted.append(ref_nodes[i].id)
        elif j < len(gen_nodes):
            inserted.append(gen_nodes[j].id)

    total = 0.0
    for ref_id, gen_id in mapping.items():
        # a cost of 0.0 is a perfect match, so test for None explicitly;
        # substituting across kinds would cost a deletion plus an insertion
        cost_value = substitution_cost(reference.nodes[ref_id], generated.nodes[gen_id], threshold)
        total += 2.0 if cost_value is None else cost_value
    total += len(deleted) + len(inserted)
    generated_flows = set(generated.flows)
    kept = {(mapping.get(s), mapping.get(t)) for s, t in reference.flows}
    total += sum(1 for pair in kept if pair not in generated_flows)          # reference edges removed
    total += sum(1 for flow in generated_flows if flow not in kept)          # generated edges added

    largest = max(reference.size(), generated.size())
    combined = reference.size() + generated.size()
    relative = total / largest if largest else 0.0
    return {"ged": round(total, 2),
            # the paper's Eq. 12: GED / max(|G1|, |G2|). It can exceed 1, because
            # an edit path may cost more than the larger graph's size.
            "rged": round(relative, 3),
            "similarity": round(1 - min(relative, 1.0), 3),
            # normalised by the two sizes together, which is bounded by 1
            "rged_combined": round(total / combined, 3) if combined else 0.0,
            "similarity_combined": round(1 - total / combined, 3) if combined else 0.0,
            "reference_size": reference.size(), "generated_size": generated.size(),
            "note": "upper bound: cost of an optimal-assignment edit path"}


def to_markdown(result, title=""):
    lines = [f"### {title}" if title else "",
             "| Element | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for element in ("tasks", "gateways", "edges"):
        m = result[element]
        lines.append(f"| {element.capitalize()} | {m['tp']} | {m['fp']} | {m['fn']} | "
                     f"{m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |")
    g = result["ged"]
    lines.append(f"\nGED {g['ged']} ({g['note']}); sizes {g['reference_size']} and {g['generated_size']}")
    lines.append(f"RGED {g['rged']} / similarity {g['similarity']} (paper Eq. 12, over the larger model); "
                 f"{g['rged_combined']} / {g['similarity_combined']} (over both sizes)")
    return "\n".join(line for line in lines if line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", required=True)
    ap.add_argument("--generated", required=True)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"label similarity needed to match two tasks (default {DEFAULT_THRESHOLD})")
    ap.add_argument("--json", help="write the full result, including the task mapping")
    ap.add_argument("--title", default="")
    args = ap.parse_args()
    result = compare(read_bpmn(args.reference), read_bpmn(args.generated), args.threshold)
    print(to_markdown(result, args.title))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
