"""Generate a BPMN 2.0 diagram from finder3's extraction output.

    python3 -m text2bpmn.generate EXTRACTION -o OUT.bpmn [--report OUT.json]

The report lists every change the Validation Layer made to the extractor's
output, so a generated diagram can always be traced back to it.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from text2bpmn.bpmn_xml import to_xml
from text2bpmn.load import load_extraction
from text2bpmn.structure import validate


def generate(extraction_path, name=None):
    extraction = load_extraction(extraction_path)
    process = validate(extraction)
    xml = to_xml(process, name or Path(extraction_path).stem)
    report = {
        "input": str(extraction_path),
        "input_counts": dict(Counter(e["type"] for e in extraction["elements"]), flows=len(extraction["flows"])),
        "output_counts": dict(Counter(n.kind for n in process.nodes.values()), flows=len(process.flows)),
        "lanes": list(dict.fromkeys(n.lane for n in process.nodes.values())),
        "rule_counts": dict(Counter(rule for rule, _ in process.log)),
        "changes": [{"rule": rule, "change": text} for rule, text in process.log],
    }
    return xml, report


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("extraction", help="finder3 output (JSON or the printed dict)")
    ap.add_argument("-o", "--output", required=True, help="BPMN file to write")
    ap.add_argument("--report", help="write the Validation Layer report as JSON")
    ap.add_argument("--name", help="process name shown on the pool")
    args = ap.parse_args()
    xml, report = generate(args.extraction, args.name)
    Path(args.output).write_text(xml, encoding="utf-8")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{args.output}: {report['output_counts']} (from {report['input_counts']})")
    print("rules applied:", report["rule_counts"])


if __name__ == "__main__":
    main()
