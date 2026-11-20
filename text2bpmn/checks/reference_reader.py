"""Read a reference BPMN model into the extraction shape ontology.populate takes.

The reference models are BPMN already, so they are populated with
validate=False: no Validation Layer rule restructures them. What the reader
keeps that text2bpmn.compare.read_bpmn does not: each node's lane, each flow's
name, inclusive gateways, and each flow's relation type.

A relation type is what the extractor would have read the flow from. A flow
leaving a parallel split is PARALLEL. A named flow leaving an exclusive or
inclusive split is TRUE_BRANCH or FALSE_BRANCH by the committed table
reference_branches.csv, which is the only place a reference's free-text
outcome names ("not eligible", "Mild") become true or false; a named branch
the table does not list is an error, not a guess. Everything else is SEQUENCE.
"""
import csv
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from text2bpmn.compare import TASK_TAGS

M = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
TABLE = Path(__file__).parent / "reference_branches.csv"
KINDS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "startEvent", "endEvent"}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def branch_table(case, path=TABLE):
    with open(path, newline="", encoding="utf-8") as f:
        return {clean(row["branch"]).lower(): row["outcome"] == "true"
                for row in csv.DictReader(f) if row["case"] == case}


def read_reference(path, case):
    branches = branch_table(case)
    process = ET.parse(path).getroot().find(M + "process")
    lane_of = {}
    for lane in process.iter(M + "lane"):
        for ref in lane.findall(M + "flowNodeRef"):
            lane_of[clean(ref.text)] = clean(lane.get("name"))
    elements = []
    for element in process:
        tag = element.tag.replace(M, "")
        if tag in TASK_TAGS or tag in KINDS or tag.endswith("Event"):
            elements.append({"id": element.get("id"), "name": clean(element.get("name")),
                             "type": "task" if tag in TASK_TAGS else tag,
                             "lane": lane_of.get(element.get("id"), "")})
    kind = {e["id"]: e["type"] for e in elements}
    flows = [f for f in process.iter(M + "sequenceFlow")]
    out_degree = Counter(f.get("sourceRef") for f in flows)
    extracted = []
    for f in flows:
        source, name = f.get("sourceRef"), clean(f.get("name"))
        relation = "SEQUENCE"
        if out_degree[source] >= 2 and kind.get(source) == "parallelGateway":
            relation = "PARALLEL"
        elif out_degree[source] >= 2 and kind.get(source) in ("exclusiveGateway", "inclusiveGateway") and name:
            if name.lower() not in branches:
                raise KeyError(f"{path}: branch {name!r} is not in {TABLE.name} for {case}")
            relation = "TRUE_BRANCH" if branches[name.lower()] else "FALSE_BRANCH"
        extracted.append({"id": f.get("id"), "source": source, "target": f.get("targetRef"),
                          "name": name, "relation": relation})
    return {"name": f"reference {case}", "participants": sorted(set(lane_of.values())),
            "elements": elements, "flows": extracted}
