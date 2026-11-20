"""Measure the pipeline's sequence and branch construction against PET's flows.

    python3 -m text2bpmn.pet_flow_eval [--documents 45] [--json OUT.json]

Edges are the weakest measure in this work: 0.06 to 0.31 across three case
studies. PET annotates 675 `flow` relations over 45 documents, which is the
evidence those three documents cannot give.

PET's **gold** entity spans go into the real structuring path with the real
relation classifier, so what is measured is how the pipeline builds edges, not
whether the recogniser found the spans.

Three shapes of PET flow are scored, by what they connect:

| shape | instances | what it tests |
|---|---|---|
| Activity -> Activity | 334 | a plain sequence edge |
| Activity -> XOR Gateway | 78 | entering a decision |
| Condition Specification -> Activity | 79 | leaving a branch |

The fourth shape, XOR Gateway -> Condition Specification (80), is condition
folding and is already measured in text2bpmn/pet_rules_eval.py.

A second measure, `all_flows`, scores every PET flow but that one: the three
shapes above and the 104 others, 72 of them XOR Gateway -> Activity, which is
how PET annotates a branch that an else-marker opens ("Otherwise" -> "rejects").
The first measure leaves those out, so a model that builds such a branch is
charged for it as an edge PET does not annotate. In the second, a gateway
mention that has no element of its own -- an else-marker, or a second mention
of a decision (text2bpmn/decisions.py) -- stands for the nearest decision
before it, as a folded condition does in both; a flow between two mentions
PET links as `same gateway` is neither right nor wrong. It needs a job file
with `all_flows` (text2bpmn/pet_export.py since 2026-11-11).

A third, `concurrency` (relation idea 3, 2026-11-12), scores what neither
flow measure can: whether steps PET puts side by side are side by side in the
model. PET annotates a parallel block as flows from an AND Gateway mention to
the first step of each line of work (8 mentions, 10 pairs of lines on the 45
documents). Each pair of those targets is a gold concurrent pair; each pair of
targets of one parallel split in the model (a parallel gateway, or a task
with several unlabelled outgoing flows, which the Validation Layer makes one)
is a built pair, counted when both are elements PET's spans map to.

Two things have to be reconciled before an edge can be compared:

- **A folded condition is no longer a node.** The pipeline merges a Condition
  Specification into the gateway it qualifies, so PET's "condition -> activity"
  edge is the pipeline's "gateway -> activity". The condition is therefore
  mapped to the gateway that absorbed it, by the same rule that folded it: the
  nearest gateway before it.
- **The pipeline inserts gateways.** A block's split and join sit between the
  steps they coordinate, so two activities PET connects directly may be two
  edges apart. An edge counts as built when it is direct or passes through
  exactly one gateway node, which is the same definition the competency
  questions use for a handover.
"""
import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from text2bpmn.run_config import add_arguments, from_arguments

SHAPES = {("Activity", "Activity"): "sequence",
          ("Activity", "XOR Gateway"): "into a decision",
          ("Condition Specification", "Activity"): "out of a branch"}
# The second measure: every flow between steps, gateways and conditions but
# the condition folding, which is not an edge of the model
_CONTROL = ("Activity", "XOR Gateway", "AND Gateway", "Condition Specification")
ALL_SHAPES = {(a, b) for a in _CONTROL for b in _CONTROL} - {("XOR Gateway", "Condition Specification")}


def _prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3),
            "recall": round(recall, 3), "f1": round(f1, 3)}


def _element_for(span, spans, elements_by_id):
    """The element that represents this gold span, or None.

    A folded condition has no element of its own; it is represented by the
    nearest gateway before it, which is the one the rule folds it into.
    """
    own = elements_by_id.get(span.get("id"))
    if own is not None:
        return own
    if span["entity_group"] == "Condition Specification":
        before = [s for s in spans
                  if s.get("type") == "exclusiveGateway" and s["start"] < span["start"]
                  and s.get("id") in elements_by_id]
        if before:
            return elements_by_id[max(before, key=lambda s: s["start"])["id"]]
    return None


def _element_or_decision(span, spans, elements):
    """As _element_for, and a gateway mention with no element of its own
    stands for the nearest decision before it."""
    own = elements.get(span.get("id"))
    if own is not None:
        return own
    if span["entity_group"] in ("Condition Specification", "XOR Gateway"):
        before = [s for s in spans
                  if s.get("type") == "exclusiveGateway" and s["start"] < span["start"]
                  and s.get("id") in elements]
        if before:
            return elements[max(before, key=lambda s: s["start"])["id"]]
    return None


def score_all_flows(job, spans, elements, flows):
    """The second measure: counts over every PET flow but the folding."""
    at = {(s["start"], s["end"]): s for s in spans}

    def element(offsets):
        span = at.get(tuple(offsets))
        return _element_or_decision(span, spans, elements) if span else None

    counts, annotated, same = Counter(), set(), set()
    for flow in job["all_flows"]:
        s, t = element(flow["source"]), element(flow["target"])
        if s is None or t is None:
            counts["unmapped"] += 1
        elif s["id"] != t["id"]:  # an else-marker's flow from its own decision
            annotated.add((s["id"], t["id"]))
    for a, b in job.get("same_gateway", []):
        s, t = element(a), element(b)
        if s is not None and t is not None:
            same |= {(s["id"], t["id"]), (t["id"], s["id"])}
    gateways = {e["id"] for e in elements.values() if e["type"].endswith("Gateway")}
    for s, t in annotated:
        counts["tp" if _connected(flows, s, t, gateways) else "fn"] += 1
    mapped = {s["id"] for s in spans if s.get("id") in elements}
    for flow in flows:
        pair = (flow["source"], flow["target"])
        if pair[0] in mapped and pair[1] in mapped and pair not in annotated and pair not in same:
            counts["fp"] += 1
    return dict(counts)


def score_concurrency(job, spans, elements, flows):
    """The third measure: pairs of steps in parallel lines of work."""
    at = {(s["start"], s["end"]): s for s in spans}

    def element(offsets):
        span = at.get(tuple(offsets))
        return _element_or_decision(span, spans, elements) if span else None

    counts, gold, targets = Counter(), set(), defaultdict(list)
    for flow in job["all_flows"]:
        if flow.get("source_label") == "AND Gateway":
            targets[tuple(flow["source"])].append(flow["target"])
    for offsets in targets.values():
        mapped = [element(t) for t in offsets]
        counts["unmapped"] += sum(m is None for m in mapped)
        gold |= {frozenset(pair) for pair in combinations(sorted({m["id"] for m in mapped if m}), 2)}
    mapped_ids = {s["id"] for s in spans if s.get("id") in elements}
    outgoing = defaultdict(list)
    for flow in flows:
        outgoing[flow["source"]].append(flow)
    built = set()
    for source, outs in outgoing.items():
        kind = elements[source]["type"] if source in elements else ""
        if len(outs) < 2 or not (kind == "parallelGateway" or (not kind.endswith("Gateway")
                                                                and not any(f.get("name") for f in outs))):
            continue
        ends = sorted({f["target"] for f in outs if f["target"] in mapped_ids})
        built |= {frozenset(pair) for pair in combinations(ends, 2)}
    counts["tp"] = len(gold & built)
    counts["fn"] = len(gold - built)
    counts["fp"] = len(built - gold)
    return dict(counts)


def _connected(flows, source, target, gateways):
    """Direct, or through exactly one gateway."""
    direct = {(f["source"], f["target"]) for f in flows}
    if (source, target) in direct:
        return True
    return any((source, middle) in direct and (middle, target) in direct
               for middle in gateways)


# the same mapping text2bpmn/pet_rules_eval.py makes, by label alone, so a job
# file carries everything the scorer needs and the corpus is not reread
def _span_type(label):
    from text2bpmn.finder3 import CONDITION_LABELS
    if label in ("XOR Gateway", *CONDITION_LABELS):
        return "exclusiveGateway"
    if label in ("AND Gateway", "Parallel Gateway"):
        return "parallelGateway"
    if label in ("Actor", "AGENT"):
        return "Lane"
    return "task"


def score_job(extractor, job, keep=None):
    """One document: run the pipeline on its gold spans, score its gold flows.

    Returns the counts for this document alone, so a long run can write them
    out as it goes and be resumed or read while it is still going. With
    `keep`, a dict, the pipeline's own result is left in keep["result"], so
    the model can be saved and scored again later.
    """
    result = extractor.process_text(job["text"], entities={
        "text": job["text"],
        "spans": [{"start": s["start"], "end": s["end"], "label": s["label"], "score": 1.0}
                  for s in job["spans"]],
        "source": "PET gold spans"})
    if keep is not None:
        keep["result"] = result
    return score_result(job, result)


def score_concurrency_saved(job, saved):
    """The third measure for a document of a run made before it, from the
    process.json the run saved."""
    return score_result(job, saved)["concurrency"]


def score_result(job, result):
    """score_job's counts from the pipeline's result for one document, or
    from the process.json a PET run saved for it, with no LLM."""
    spans = [{"entity_group": s["label"], "start": s["start"], "end": s["end"],
              "word": job["text"][s["start"]:s["end"]], "score": 1.0,
              "type": _span_type(s["label"]), "id": index}
             for index, s in enumerate(job["spans"])]
    data_out = result["structured_data"]
    elements = {e["id"]: e for e in data_out["elements"]}
    used = {(u["start"], u["end"]): u for u in result["entities_used"]
            if u.get("start") is not None}
    for span in spans:
        match = used.get((span["start"], span["end"]))
        span["id"] = match["id"] if match else None
        if match:
            span["type"] = match.get("type", span.get("type"))

    at_offset = {(sp["start"], sp["end"]): sp for sp in spans}
    gateways = {e["id"] for e in data_out["elements"] if e["type"].endswith("Gateway")}
    counts, by_shape, misses = Counter(), defaultdict(Counter), []
    gold_edges = set()
    for flow in job["gold_flows"]:
        shape = flow["shape"]
        source = at_offset.get(tuple(flow["source"]))
        target = at_offset.get(tuple(flow["target"]))
        s = _element_for(source, spans, elements) if source else None
        t = _element_for(target, spans, elements) if target else None
        if s is None or t is None:
            counts["unmapped"] += 1
            by_shape[shape]["unmapped"] += 1
            continue
        gold_edges.add((s["id"], t["id"], shape))
        if _connected(data_out["flows"], s["id"], t["id"], gateways):
            counts["tp"] += 1
            by_shape[shape]["tp"] += 1
        else:
            counts["fn"] += 1
            by_shape[shape]["fn"] += 1
            misses.append((job["name"], s.get("name"), t.get("name"), shape))

    mapped = {s["id"]: s for s in spans if s.get("id") in elements}
    annotated = {(s, t) for s, t, _ in gold_edges}
    for flow in data_out["flows"]:
        if flow["source"] in mapped and flow["target"] in mapped \
                and (flow["source"], flow["target"]) not in annotated:
            counts["fp"] += 1

    parsing = result["relation_parsing"]
    record = {"document": job["name"], "spans": len(spans),
              "counts": dict(counts), "by_shape": {k: dict(v) for k, v in by_shape.items()},
              "misses": misses,
              "relation_calls": parsing["calls"],
              "relation_failures": parsing["failures"],
              "answered_pairs": parsing["calls"] - parsing["failures"]}
    if "all_flows" in job:
        record["all_flows"] = score_all_flows(job, spans, elements, data_out["flows"])
        record["concurrency"] = score_concurrency(job, spans, elements, data_out["flows"])
    if "soundness_gate" in data_out:  # relation idea 3: whether the gate had to undo anything
        gate = data_out["soundness_gate"]
        record["soundness_gate"] = {"sound": gate["sound"], "undone": gate["undone"]}
    return record


def evaluate(limit=None, data="pet_data/PETv1.1-relations.json", jobs_path=None,
             records_path=None, config=None):
    """Score every job, writing each document's record as it finishes.

    `jobs_path` reads the exported bundle (text2bpmn/pet_export.py) and never
    touches the corpus; without it the bundle is built here from `data`.
    `records_path` is a JSONL that is appended to and resumed from. The prompt
    is `config.prompt`, like every other run setting.
    """
    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    config = config or RunConfig()
    if jobs_path:
        bundle = json.loads(Path(jobs_path).read_text(encoding="utf-8"))
    else:
        from text2bpmn.pet_export import export
        bundle = export(data)
    all_jobs = bundle["jobs"][:limit]

    records, done = [], set()
    if records_path and Path(records_path).exists():
        for line in Path(records_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                records.append(record)
                done.add(record["document"])
        print(f"resuming: {len(done)} documents already scored", flush=True)

    extractor = BPMNHybridExtractor(config=config, ner_model_path=None)
    for index, job in enumerate(all_jobs, 1):
        if job["name"] in done:
            continue
        print(f"[{index}/{len(all_jobs)}] {job['name']}: {len(job['spans'])} gold spans",
              flush=True)
        record = score_job(extractor, job)
        records.append(record)
        if records_path:
            with open(records_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        c = record["counts"]
        print(f"   built {c.get('tp', 0)}, missed {c.get('fn', 0)}, "
              f"{record['relation_failures']}/{record['relation_calls']} calls failed",
              flush=True)
    result = aggregate(records, bundle, getattr(extractor, "run_record", None))
    result["prompt"] = config.prompt
    return result


def aggregate(records, bundle=None, run_record=None):
    """The whole result from the per-document records."""
    totals, by_shape, misses, calls, answered, failures = \
        Counter(), defaultdict(Counter), [], 0, 0, 0
    every = Counter() if records and all("all_flows" in r for r in records) else None
    side = Counter() if records and all("concurrency" in r for r in records) else None
    for record in records:
        totals.update(record["counts"])
        if every is not None:
            every.update(record["all_flows"])
        if side is not None:
            side.update(record["concurrency"])
        for shape, counts in record["by_shape"].items():
            by_shape[shape].update(counts)
        misses.extend(tuple(m) for m in record["misses"])
        calls += record["relation_calls"]
        answered += record["answered_pairs"]
        failures += record["relation_failures"]
    result = {"documents": len(records), "relation_calls": calls,
            "relation_answered": answered, "relation_failures": failures,
            "relation_failure_rate": round(failures / calls, 3) if calls else 0.0,
            "overall": _prf(totals["tp"], totals["fp"], totals["fn"]),
            "unmapped_gold_edges": totals["unmapped"],
            "by_shape": {shape: _prf(c["tp"], 0, c["fn"]) | {"unmapped": c["unmapped"]}
                         for shape, c in by_shape.items()},
            "examples_of_missing_edges": misses[:12],
            "jobs": {k: v for k, v in (bundle or {}).items() if k != "jobs"},
            "run": run_record}
    if every is not None:
        result["all_flows"] = _prf(every["tp"], every["fp"], every["fn"]) | {"unmapped": every["unmapped"]}
    if side is not None:
        result["concurrency"] = _prf(side["tp"], side["fp"], side["fn"]) | {"unmapped": side["unmapped"]}
    return result


def to_markdown(result):
    overall = result["overall"]
    lines = [f"The pipeline's edges against PET's `flow` relations, "
             f"{result['documents']} documents, PET's gold entity spans as input and the "
             f"real relation classifier, {result['relation_calls']} calls.", "",
             f"Recall is the share of annotated flows the pipeline builds; an edge counts "
             f"when it is direct or passes through one gateway.", "",
             "| Flow shape | built | missed | recall |", "|---|---|---|---|"]
    for shape, scores in result["by_shape"].items():
        lines.append(f"| {shape} | {scores['tp']} | {scores['fn']} | {scores['recall']} |")
    lines += [f"| **all shapes** | {overall['tp']} | {overall['fn']} | **{overall['recall']}** |",
              "",
              f"Edges the pipeline adds between annotated elements that PET does not "
              f"annotate: {overall['fp']}, giving precision {overall['precision']} and "
              f"F1 {overall['f1']}.",
              "",
              f"Gold edges whose endpoints could not be mapped to an element: "
              f"{result['unmapped_gold_edges']}."]
    if result.get("all_flows"):
        a = result["all_flows"]
        lines += ["", f"On every PET flow but the condition folding (the second measure): "
                      f"{a['tp']} built, {a['fn']} missed, {a['fp']} not annotated, "
                      f"{a['unmapped']} unmapped; precision {a['precision']}, recall {a['recall']}, "
                      f"F1 {a['f1']}."]
    if result.get("concurrency"):
        c = result["concurrency"]
        lines += ["", f"Pairs of steps PET puts in parallel lines of work (the third measure): "
                      f"{c['tp']} built side by side, {c['fn']} not, {c['fp']} side by side where PET "
                      f"has no such pair, {c['unmapped']} gold targets unmapped."]
    if result.get("relation_calls"):
        lines += ["",
                  f"The relation classifier was asked {result['relation_calls']} times and "
                  f"answered {result['relation_answered']} of them; "
                  f"{result['relation_failures']} calls failed "
                  f"({result['relation_failure_rate']:.1%}). A failed call returns UNKNOWN "
                  f"and no edge is built, so those land as missing flows: the recall above "
                  f"is the deployed system's, and it charges the pipeline for answers the "
                  f"model never gave. See provenance/relation_failures_2026-10-07.md."]
    if result["examples_of_missing_edges"]:
        lines += ["", "Examples of flows the pipeline does not build:"]
        for document, source, target, shape in result["examples_of_missing_edges"]:
            lines.append(f"- {document}: {source!r} -> {target!r} ({shape})")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--documents", type=int, default=None,
                    help="score only this many documents, for a quick check")
    ap.add_argument("--data", default="pet_data/PETv1.1-relations.json")
    ap.add_argument("--jobs", help="an exported job file (text2bpmn.pet_export); "
                                   "with it the corpus is never read")
    ap.add_argument("--records", help="JSONL of per-document results, appended to as "
                                      "the run goes and resumed from if it is restarted")
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    add_arguments(ap)  # includes --prompt
    args = ap.parse_args()
    result = evaluate(args.documents, args.data, args.jobs, args.records,
                      from_arguments(args))
    text = to_markdown(result)
    print("\n" + text)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n✅ Wrote {args.json}")
    if args.markdown:
        Path(args.markdown).write_text(text + "\n", encoding="utf-8")
        print(f"✅ Wrote {args.markdown}")


if __name__ == "__main__":
    main()
