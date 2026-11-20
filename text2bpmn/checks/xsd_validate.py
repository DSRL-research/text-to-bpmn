"""Task 2: validate every BPMN model in a folder against the OMG BPMN 2.0.2 XSD.

    python3 -m text2bpmn.checks.xsd_validate runs/pilot [runs/pilot_scripted ...]

Every `*.bpmn` file below each folder is validated with lxml's XMLSchema,
built from text2bpmn/checks/schemas/BPMN20.xsd (see the README there for the
source and checksums). Per model: valid or not, and every error with its line
and message. Errors are also grouped by type, with the variable parts of the
message (ids, values) masked so that the same problem counts once.
"""
import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

from text2bpmn.checks.common import header, provenance, write

SCHEMA = Path(__file__).parent / "schemas" / "BPMN20.xsd"


def error_type(message):
    """The message with quoted values masked: one key per kind of problem."""
    return re.sub(r"'[^']*'", "'…'", message)


def validate(schema, path):
    try:
        document = etree.parse(str(path))
    except etree.XMLSyntaxError as e:
        return {"valid": False, "errors": [{"line": e.lineno, "message": f"not well-formed: {e.msg}"}]}
    valid = schema.validate(document)
    return {"valid": valid, "errors": [{"line": e.line, "message": e.message} for e in schema.error_log]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--out", default="runs/checks/xsd")
    args = ap.parse_args()
    schema = etree.XMLSchema(etree.parse(str(SCHEMA)))
    record = provenance(schema=str(SCHEMA), folders=args.folders)
    result = {"provenance": record, "folders": {}}
    lines = header("BPMN 2.0.2 XSD validation", record)
    for folder in args.folders:
        models = {str(p.relative_to(folder)): validate(schema, p) for p in sorted(Path(folder).rglob("*.bpmn"))}
        kinds, where = Counter(), defaultdict(set)
        for name, outcome in models.items():
            for e in outcome["errors"]:
                kinds[error_type(e["message"])] += 1
                where[error_type(e["message"])].add(name.split("/")[0])
        valid = sum(m["valid"] for m in models.values())
        result["folders"][folder] = {"models": len(models), "valid": valid,
                                     "error_types": [{"type": k, "count": n, "models": len(where[k])}
                                                     for k, n in kinds.most_common()],
                                     "per_model": models}
        lines += [f"## {folder}", "", f"{valid} of {len(models)} models are valid.", ""]
        if kinds:
            lines += ["| error | occurrences | models |", "|---|---|---|"]
            lines += [f"| {k} | {n} | {len(where[k])} |" for k, n in kinds.most_common()]
            lines.append("")
    print("wrote", write(args.out, "xsd_validation", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
