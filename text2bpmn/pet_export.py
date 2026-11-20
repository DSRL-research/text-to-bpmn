"""Export the PET flow-evaluation jobs, so the LLM half can run elsewhere.

    python3 -m text2bpmn.pet_export -o text2bpmn/baselines/pet_jobs.json

One job per document: the text, the gold entity spans the pipeline is given,
and the gold `flow` relations it will be scored against: `gold_flows`, the
three shapes text2bpmn/pet_flow_eval.py scores first, and `all_flows`, every
flow but the folded gateway -> condition, with `same_gateway`, PET's links
between two mentions of one decision, for its second measure. Nothing in the file
needs a model to produce, so this runs on any machine in a second.

What this buys: the evaluation's expensive half is the relation classifier,
one LLM call per candidate pair. The entity recogniser never runs at all --
PET's gold spans are the input, by design, so that a missing edge is the
pipeline's reasoning and not a missed span. Exporting the jobs means the
machine that does the calls needs neither the 1.1 GB checkpoint nor the
corpus: it needs this file, the pipeline, spaCy and an LLM.

Offsets are into `text`, which is the document's tokens joined by single
spaces -- the same string `text2bpmn/pet_rules_eval.py` builds, so a span
exported here and a span scored there are the same span.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from text2bpmn.pet_flow_eval import ALL_SHAPES, SHAPES
from text2bpmn.pet_rules_eval import PET_DEFAULT, load_documents


def export(path=PET_DEFAULT, limit=None):
    documents = load_documents(path)[:limit]
    jobs, counts = [], Counter()
    for document in documents:
        spans = [{"start": s["start"], "end": s["end"], "label": s["entity_group"],
                  "score": 1.0, "sentence": s["sentence"]}
                 for s in document["spans"]]
        flows, all_flows, same_gateway = [], [], []
        for kind, source, target in document["relations"]:
            pair = (source["entity_group"], target["entity_group"])
            if kind == "flow" and pair in ALL_SHAPES:
                all_flows.append({"source": [source["start"], source["end"]],
                                  "target": [target["start"], target["end"]],
                                  "source_label": pair[0], "target_label": pair[1]})
                counts["all flows"] += 1
            if kind == "same gateway":
                same_gateway.append([[source["start"], source["end"]], [target["start"], target["end"]]])
                counts["same gateway"] += 1
            shape = SHAPES.get(pair)
            if kind != "flow" or shape is None:
                continue
            flows.append({"source": [source["start"], source["end"]],
                          "target": [target["start"], target["end"]],
                          "source_label": source["entity_group"],
                          "target_label": target["entity_group"],
                          "shape": shape})
            counts[shape] += 1
        jobs.append({"name": document["name"], "text": document["text"],
                     "spans": spans, "gold_flows": flows,
                     "all_flows": all_flows, "same_gateway": same_gateway})
        counts["spans"] += len(spans)

    # biggest first: a run that is cut short has then covered the most work,
    # and the slowest document is not left to the end
    jobs.sort(key=lambda job: -len(job["spans"]))
    return {"source": str(path), "documents": len(jobs),
            "spans": counts["spans"],
            "scored_flows": {shape: counts[shape] for shape in SHAPES.values()},
            "all_flows": counts["all flows"], "same_gateway_links": counts["same gateway"],
            "span_order": "documents sorted by span count, largest first",
            "jobs": jobs}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=PET_DEFAULT)
    ap.add_argument("--documents", type=int, default=None)
    ap.add_argument("-o", "--output", default="text2bpmn/baselines/pet_jobs.json")
    args = ap.parse_args()
    bundle = export(args.data, args.documents)
    Path(args.output).write_text(json.dumps(bundle, indent=1, ensure_ascii=False),
                                 encoding="utf-8")
    size = Path(args.output).stat().st_size
    print(f"✅ Wrote {args.output} ({size/1024:.0f} KB)")
    print(f"   {bundle['documents']} documents, {bundle['spans']} gold spans, "
          f"{sum(bundle['scored_flows'].values())} scored flows")
    for shape, n in bundle["scored_flows"].items():
        print(f"     {shape:18s} {n}")


if __name__ == "__main__":
    main()
