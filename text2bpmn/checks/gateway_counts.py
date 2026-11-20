"""How many decisions and parallel gateways a pilot's models contain, and
whether the extractor or the Validation Layer put them there.

    python3 -m text2bpmn.checks.gateway_counts runs/pilot runs/pilot_scripted

A gateway the Validation Layer inserted has an id Gateway_split_N or
Gateway_join_N (structure.Process.insert_node); every other gateway comes from
finder3: a recognised XOR or AND Gateway mention, a Condition Specification
with no gateway before it, or the split and join of a parallel block.
"""
import argparse
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from text2bpmn.checks.common import documents, header, provenance, write

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
KINDS = ("exclusiveGateway", "parallelGateway")


def count(path):
    root = ET.parse(path).getroot()
    found = Counter()
    for kind in KINDS:
        for element in root.iter(BPMN + kind):
            source = "validation" if element.get("id", "").startswith("Gateway_") else "extractor"
            found[f"{kind}/{source}"] += 1
    return dict(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pilots", nargs="+")
    ap.add_argument("--out", default="runs/checks/gateways")
    args = ap.parse_args()
    record = provenance(pilots=args.pilots)
    lines = header("Gateways in the pilot models", record)
    result = {"provenance": record, "pilots": {}}
    for pilot in args.pilots:
        per = {doc: count(path) for doc, path in documents(pilot, "model.bpmn")}
        total = Counter()
        for counts in per.values():
            total.update(counts)
        with_gateway = {k: sum(1 for c in per.values() if any(n.startswith(k) for n in c)) for k in KINDS}
        result["pilots"][pilot] = {"models": len(per), "total": dict(total),
                                   "models_with": with_gateway, "per_model": per}
        lines += [f"## {pilot} ({len(per)} models)", "",
                  "| gateway | from the extractor | inserted by validation | total | models with one |",
                  "|---|---|---|---|---|"]
        for kind in KINDS:
            a, b = total[f"{kind}/extractor"], total[f"{kind}/validation"]
            lines.append(f"| {kind} | {a} | {b} | {a + b} | {with_gateway[kind]} |")
        lines.append("")
    print("wrote", write(args.out, "gateway_counts", result, "\n".join(lines)))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
