"""The paper's figures from hand-arranged BPMN files, checked against the models they show.

    python3 -m text2bpmn.checks.figure_models ARRANGED.bpmn=MODEL.bpmn [...] [--out figures/paper]
    python3 -m text2bpmn.checks.figure_models --dir <folder with the arranged files> [--out figures/paper]

A figure may be laid out by hand (in bpmn.io or Camunda Modeler), but it must
show exactly the model that was scored. For each pair, everything outside the
BPMNDiagram section of the arranged file is compared with the model file:

- the same elements, by id, with the same tag, the same attributes (name,
  sourceRef, targetRef, processRef, isMarkerVisible ...) and the same text
  (names, documentation);
- the same references inside each element (incoming, outgoing, the lanes'
  flowNodeRef), compared as multisets, since modellers may write them in
  another order;
- the same parent, so no element moved to another lane or process.

Only the modelling tool's own stamp on <definitions> (exporter, exporterVersion
and attributes in a tool namespace) and namespace prefixes may differ. Any
added, removed, renamed or reconnected element is reported, and the figure is
then not drawn. The diagram section itself is checked only for references: every
shape and edge must point to an element of the model, and every task, gateway,
event, lane and flow must have one.

Each figure that passes is drawn by text2bpmn/render.py (the hand-arranged
positions; flows routed by the renderer) as SVG, PNG at 300 dpi and PDF, and
checked with text2bpmn/render_check.py. --dir takes the arranged files by name:
<case>_generated.bpmn against runs/final-3/cases/<case>/model.bpmn and
<case>_reference.bpmn against text2bpmn/cases/<case>/reference.bpmn.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from text2bpmn.render import render_with_notes, to_pdf, to_png
from text2bpmn.render_check import check

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
DI = "http://www.omg.org/spec/BPMN/20100524/DI"
TOOL_ATTRIBUTES = {"exporter", "exporterVersion"}   # a modeller's stamp on <definitions>
MODEL_NAMESPACES = {BPMN, "http://www.w3.org/2001/XMLSchema-instance", ""}
RUN = "runs/final-3/cases"
DRAWN = ("task", "Task", "Gateway", "Event", "lane", "participant", "sequenceFlow", "subProcess", "callActivity")


def _ns(tag):
    return tag[1:].split("}")[0] if tag.startswith("{") else ""


def _attrs(element, definitions=False):
    out = {}
    for key, value in element.attrib.items():
        if definitions and (key in TOOL_ATTRIBUTES or _ns(key) not in MODEL_NAMESPACES):
            continue
        out[key] = value
    return out


def _signature(element):
    """An element without an id (incoming, outgoing, flowNodeRef, documentation ...): what it says."""
    return (element.tag, tuple(sorted(_attrs(element).items())), (element.text or "").strip(),
            tuple(sorted(_signature(c) for c in element if c.get("id") is None)))


def semantic(path):
    """{id: description} of every element outside the BPMNDiagram, and the definitions' own attributes."""
    root = ET.parse(path).getroot()
    elements = {}

    def walk(element, parent_id):
        for child in element:
            if child.tag == f"{{{DI}}}BPMNDiagram":
                continue
            if child.get("id") is not None:
                attrs = _attrs(child)
                attrs.pop("id")
                elements[child.get("id")] = {
                    "tag": child.tag, "parent": parent_id, "attributes": attrs,
                    "text": (child.text or "").strip(),
                    "parts": Counter(_signature(c) for c in child if c.get("id") is None)}
                walk(child, child.get("id"))
            else:
                walk(child, parent_id)

    walk(root, "definitions")
    return elements, _attrs(root, definitions=True), root


def diagram_references(root, elements):
    shapes = {e.get("bpmnElement") for e in root.iter(f"{{{DI}}}BPMNShape")}
    edges = {e.get("bpmnElement") for e in root.iter(f"{{{DI}}}BPMNEdge")}
    drawn = {i for i, e in elements.items() if any(e["tag"].endswith(k) for k in DRAWN)}
    return {"shapes_or_edges_for_missing_elements": sorted((shapes | edges) - set(elements)),
            "elements_without_shape_or_edge": sorted(drawn - shapes - edges)}


def compare_models(arranged, model):
    a, a_def, a_root = semantic(arranged)
    m, m_def, _ = semantic(model)
    differences = []
    for i in sorted(set(m) - set(a)):
        differences.append(f"removed: {m[i]['tag'].split('}')[-1]} {i} ({m[i]['attributes'].get('name', '')!r})")
    for i in sorted(set(a) - set(m)):
        differences.append(f"added: {a[i]['tag'].split('}')[-1]} {i} ({a[i]['attributes'].get('name', '')!r})")
    for i in sorted(set(a) & set(m)):
        x, y = m[i], a[i]
        kind = x["tag"].split("}")[-1]
        if x["tag"] != y["tag"]:
            differences.append(f"{kind} {i}: type {kind} -> {y['tag'].split('}')[-1]}")
        for key in sorted(set(x["attributes"]) | set(y["attributes"])):
            if x["attributes"].get(key) != y["attributes"].get(key):
                differences.append(f"{kind} {i}: {key.split('}')[-1]} {x['attributes'].get(key)!r} -> "
                                   f"{y['attributes'].get(key)!r}")
        if x["text"] != y["text"]:
            differences.append(f"{kind} {i}: text {x['text']!r} -> {y['text']!r}")
        if x["parent"] != y["parent"]:
            differences.append(f"{kind} {i}: moved from {x['parent']} to {y['parent']}")
        if x["parts"] != y["parts"]:
            gone = [p[0].split("}")[-1] + ":" + p[2] for p in (x["parts"] - y["parts"]).elements()]
            new = [p[0].split("}")[-1] + ":" + p[2] for p in (y["parts"] - x["parts"]).elements()]
            differences.append(f"{kind} {i}: references removed {gone}, added {new}")
    if a_def != m_def:
        differences.append(f"definitions attributes {m_def} -> {a_def}")
    refs = diagram_references(a_root, a)
    problems = [f"diagram: {k.replace('_', ' ')}: {v}" for k, v in refs.items() if v]
    return {"arranged": str(arranged), "model": str(model), "elements": len(m),
            "identical_outside_diagram": not differences, "differences": differences,
            "diagram_problems": problems}


def pairs_from_dir(folder):
    out = []
    for path in sorted(Path(folder).glob("*.bpmn")):
        stem = path.stem
        if stem.endswith("_generated"):
            out.append((path, Path(RUN) / stem[:-len("_generated")] / "model.bpmn"))
        elif stem.endswith("_reference"):
            out.append((path, Path("text2bpmn/cases") / stem[:-len("_reference")] / "reference.bpmn"))
        else:
            print(f"skipped {path}: name it <case>_generated.bpmn or <case>_reference.bpmn", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pairs", nargs="*", help="ARRANGED.bpmn=MODEL.bpmn")
    ap.add_argument("--dir", help="a folder of <case>_generated.bpmn / <case>_reference.bpmn files")
    ap.add_argument("--out", default="figures/paper")
    ap.add_argument("--check-only", action="store_true", help="compare, draw nothing")
    args = ap.parse_args()
    pairs = [tuple(map(Path, p.split("=", 1))) for p in args.pairs] + (pairs_from_dir(args.dir) if args.dir else [])
    if not pairs:
        ap.error("give ARRANGED=MODEL pairs or --dir")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    reports, failed = [], False
    for arranged, model in pairs:
        report = compare_models(arranged, model)
        ok = report["identical_outside_diagram"] and not report["diagram_problems"]
        name = arranged.stem
        if ok and not args.check_only:
            svg, notes = render_with_notes(arranged)
            (out / f"{name}.svg").write_text(svg, encoding="utf-8")
            to_png(out / f"{name}.svg", out / f"{name}.png", 300)
            to_pdf(out / f"{name}.svg", out / f"{name}.pdf")
            drawn = check(out / f"{name}.svg")
            report.update(figure={k: str(out / f"{name}.{k}") for k in ("svg", "png", "pdf")}, render_notes=notes,
                          render_check={k: drawn[k] for k in ("crossings", "own_box", "bad_ends", "label_overlaps")})
        failed |= not ok
        reports.append(report)
        print(f"{'OK  ' if ok else 'FAIL'} {arranged} = {model}: {len(report['differences'])} difference(s)"
              + "".join(f"\n     {d}" for d in report["differences"] + report["diagram_problems"]))
    (out / "figure_check.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Hand-arranged figures checked against their models", "",
             f"`python3 -m text2bpmn.checks.figure_models {' '.join(sys.argv[1:])}`", "",
             "| figure | model | elements | identical outside the diagram | diagram references | render_check |",
             "|---|---|---|---|---|---|"]
    for r in reports:
        rc = r.get("render_check")
        lines.append(f"| `{r['arranged']}` | `{r['model']}` | {r['elements']} | "
                     f"{'yes' if r['identical_outside_diagram'] else 'NO: ' + '; '.join(r['differences'])} | "
                     f"{'ok' if not r['diagram_problems'] else '; '.join(r['diagram_problems'])} | "
                     + (", ".join(f"{k} {v}" for k, v in rc.items()) if rc else "not drawn") + " |")
    (out / "figure_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
