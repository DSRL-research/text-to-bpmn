"""Task 6: how far apart PET's gold flow relations are, counted in mentions.

    python3 -m text2bpmn.checks.window_coverage [--data pet_data/PETv1.1-relations.json]

Gold annotations only, no model. In each document the behavioural mentions --
Activity, XOR Gateway, AND Gateway, Condition Specification -- are ordered by
position, and every `flow` relation gets the signed distance from its head to
its tail in that order: 1 is the next mention, a negative distance a flow back
to an earlier one. The pipeline's window looks 3 mentions forward
(finder3.py), so distances 1 to 3 are the ones it can ask about.

The same is computed a second time with Condition Specification mentions taken
out of the order the way the pipeline takes them out: each one folds into the
nearest gateway before it (finder3._attach_conditions), and stays a mention of
its own only when there is none. A flow's end on a folded condition moves to
that gateway; a flow from a gateway to its own condition then joins a mention
to itself, has no distance, and is counted apart.

Flows with an end on another kind of mention, and flows whose head token
starts no gold span, are counted and left out.

Why 675 and not 689: the PET paper (Bellan et al., arXiv 2203.04860, Table 3)
counts 689 flow relations, but the released file read here, PETv1.1, holds 675,
all distinct and all with both ends on a gold span. The release differs from
the paper in nearly every relation type (uses 486 against 477, actor performer
399 against 313, actor recipient 166 against 164, same gateway 42 against 43),
so the gap is the dataset version, not relations this check drops.
"""
PAPER_FLOWS = 689  # PET paper, Table 3 (relation statistics)
import argparse
import json
from collections import Counter
from pathlib import Path

from text2bpmn.checks.common import header, provenance, write
from text2bpmn.pet_rules_eval import PET_DEFAULT, load_documents

BEHAVIOURAL = ("Activity", "XOR Gateway", "AND Gateway", "Condition Specification")
GATEWAYS = ("XOR Gateway", "AND Gateway")


def bucket(distance):
    if distance < 0:
        return "backward"
    if distance == 0:
        return "same mention"
    return str(distance) if distance <= 3 else ">3"


def fold_conditions(mentions):
    """Map each Condition Specification to the mention it folds into.

    As finder3._attach_conditions: the nearest kept gateway before it, where a
    Condition Specification that found none stayed a decision itself and so
    counts as a gateway for those after it.
    """
    kept, into = [], {}
    for m in mentions:
        if m["entity_group"] == "Condition Specification":
            gateway = next((g for g in reversed(kept)
                            if g["entity_group"] in GATEWAYS + ("Condition Specification",)), None)
            if gateway is not None:
                into[id(m)] = gateway
                continue
        kept.append(m)
    return kept, into


def distances(documents, fold):
    rows, skipped = [], Counter()
    for doc in documents:
        mentions = sorted((s for s in doc["spans"] if s["entity_group"] in BEHAVIOURAL), key=lambda s: s["start"])
        into = {}
        if fold:
            mentions, into = fold_conditions(mentions)
        index = {id(m): i for i, m in enumerate(mentions)}
        for kind, source, target in doc["relations"]:
            if kind != "flow":
                continue
            if source["entity_group"] not in BEHAVIOURAL or target["entity_group"] not in BEHAVIOURAL:
                skipped["an end outside the behavioural types"] += 1
                continue
            s, t = into.get(id(source), source), into.get(id(target), target)
            d = index[id(t)] - index[id(s)]
            rows.append({"document": doc["name"], "head": source["word"], "head_type": source["entity_group"],
                         "tail": target["word"], "tail_type": target["entity_group"], "distance": d,
                         "bucket": bucket(d)})
    return rows, skipped


def shares(rows, order=("1", "2", "3", ">3", "backward", "same mention")):
    rows = [r for r in rows if r["bucket"] in order]
    counts = Counter(r["bucket"] for r in rows)
    return {b: {"count": counts[b], "share": round(counts[b] / len(rows), 4) if rows else 0.0} for b in order}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=PET_DEFAULT)
    ap.add_argument("--out", default="runs/checks/window")
    args = ap.parse_args()
    raw = json.loads(Path(args.data).read_text(encoding="utf-8"))
    in_file = sum(1 for d in raw for r in d["relations"] if r["relation-type"] == "flow")
    documents = load_documents(args.data)
    mapped = sum(1 for d in documents for kind, _, _ in d["relations"] if kind == "flow")
    record = provenance(data=args.data, documents=len(documents), flow_relations_in_file=in_file,
                        flow_relations_with_both_heads_on_a_span=mapped)
    result = {"provenance": record}
    lines = header("Window coverage of PET's gold flow relations", record)
    lines += [f"{in_file} flow relations in {len(documents)} documents; {mapped} have both ends on a gold span "
              f"({in_file - mapped} have a head token that starts no span and are left out). The PET paper counts "
              f"{PAPER_FLOWS}; the released PETv1.1 file read here has {in_file}, and differs from the paper in "
              f"nearly every relation type, so the gap is the dataset version.", ""]
    for name, fold in (("all behavioural mentions", False),
                       ("Condition Specification folded into its gateway, as the pipeline does", True)):
        rows, skipped = distances(documents, fold)
        table = shares(rows)
        backward = [r for r in rows if r["distance"] < 0]
        result[name] = {"flows_used": len(rows), "skipped": dict(skipped), "shares": table,
                        "backward_examples": backward[:3], "flows": rows}
        lines += [f"## Ordering: {name}", "",
                  f"{len(rows)} flows used" + "".join(f"; {n} left out: {why}" for why, n in skipped.items()) + ".", "",
                  "| distance | flows | share |", "|---|---|---|"]
        lines += [f"| {b} | {v['count']} | {v['share']:.1%} |" for b, v in table.items()]
        within = sum(table[b]["count"] for b in ("1", "2", "3"))
        lines += ["", f"Within the window (forward, 1 to 3): {within} of {len(rows)} ({within / len(rows):.1%})."]
        absorbed = table["same mention"]["count"]
        if absorbed:
            lines.append(f"Leaving out the {absorbed} flows from a gateway to its own folded condition, which "
                         f"need no relation: {within} of {len(rows) - absorbed} "
                         f"({within / (len(rows) - absorbed):.1%}).")
        if absorbed:
            directed = shares(rows, ("1", "2", "3", ">3", "backward"))
            result[name]["shares_without_absorbed"] = directed
            lines += ["", f"The same {len(rows) - absorbed} flows by distance, shares summing to 100%:", "",
                      "| distance | flows | share |", "|---|---|---|"]
            lines += [f"| {b} | {v['count']} | {v['share']:.1%} |" for b, v in directed.items()]
        kinds = Counter(f"{r['head_type']} -> {r['tail_type']}" for r in backward)
        result[name]["backward_by_type"] = dict(kinds.most_common())
        lines += ["", "Backward flows by head and tail type: "
                  + ", ".join(f"{k} {n}" for k, n in kinds.most_common()) + ".", ""]
        if backward:
            lines += ["Backward, first three:", ""]
            lines += [f"- {r['document']}: {r['head']!r} ({r['head_type']}) -> {r['tail']!r} ({r['tail_type']}), "
                      f"distance {r['distance']}" for r in backward[:3]]
            lines.append("")
    print("wrote", write(args.out, "window_coverage", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
