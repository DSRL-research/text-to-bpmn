"""figure_models: a hand-arranged file passes only if it shows exactly the scored model."""
import xml.etree.ElementTree as ET
from pathlib import Path

from text2bpmn.checks.figure_models import compare_models

REPO = Path(__file__).resolve().parents[2]
MODEL = REPO / "runs/final-3/cases/loan/model.bpmn"
B = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"


def arranged(tmp_path, change=None):
    """What a modeller does on export: other namespace prefixes, its stamp on
    <definitions>, shapes moved, references written in another order."""
    ET.register_namespace("semantic", B[1:-1])
    tree = ET.parse(MODEL)
    root = tree.getroot()
    root.set("exporter", "Camunda Modeler")
    root.set("exporterVersion", "5.0.0")
    for bounds in root.iter(f"{DC}Bounds"):
        bounds.set("x", str(float(bounds.get("x")) + 37))
    for lane in root.iter(f"{B}lane"):
        refs = list(lane.findall(f"{B}flowNodeRef"))
        for r in refs:
            lane.remove(r)
        for r in reversed(refs):
            lane.append(r)
    if change:
        change(root)
    path = tmp_path / "loan_generated.bpmn"
    tree.write(path, encoding="utf-8", xml_declaration=True)
    ET.register_namespace("bpmn", B[1:-1])
    return path


def task(root, name):
    return next(t for t in root.iter(f"{B}task") if t.get("name") == name)


def test_a_layout_change_alone_passes(tmp_path):
    report = compare_models(arranged(tmp_path), MODEL)
    assert report["identical_outside_diagram"], report["differences"]
    assert not report["diagram_problems"]


def test_a_renamed_task_is_reported(tmp_path):
    report = compare_models(arranged(tmp_path, lambda r: task(r, "Sent").set("name", "Send acceptance pack")), MODEL)
    assert not report["identical_outside_diagram"]
    assert any("'Sent' -> 'Send acceptance pack'" in d for d in report["differences"])


def test_a_reconnected_flow_is_reported(tmp_path):
    def reconnect(root):
        flow = next(f for f in root.iter(f"{B}sequenceFlow") if f.get("targetRef") == "Activity_c7a980a9")
        flow.set("targetRef", "Gateway_join_1")
    report = compare_models(arranged(tmp_path, reconnect), MODEL)
    assert any("targetRef" in d for d in report["differences"])


def test_a_deleted_task_is_reported_and_its_shape_left_dangling(tmp_path):
    def delete(root):
        process = next(root.iter(f"{B}process"))
        process.remove(task(root, "Sent"))
    report = compare_models(arranged(tmp_path, delete), MODEL)
    assert any(d.startswith("removed: task Activity_c7a980a9") for d in report["differences"])
    assert report["diagram_problems"]


def test_a_task_moved_to_another_lane_is_reported(tmp_path):
    def move(root):
        lanes = list(root.iter(f"{B}lane"))
        ref = next(r for r in lanes[2].findall(f"{B}flowNodeRef") if r.text == "Activity_c7a980a9")
        lanes[2].remove(ref)
        lanes[0].append(ref)
    report = compare_models(arranged(tmp_path, move), MODEL)
    assert any("flowNodeRef:Activity_c7a980a9" in d for d in report["differences"])
