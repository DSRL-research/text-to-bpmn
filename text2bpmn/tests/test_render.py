"""The renderer routes every flow around the boxes and keeps names off boxes,
other names and lines; render_check finds it when either goes wrong."""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from text2bpmn.render import render
from text2bpmn.render_check import check

REPO = Path(__file__).resolve().parents[2]
FILES = ([REPO / "runs/final-3/cases" / case / "model.bpmn" for case in ("loan", "goods_dispatch", "healthcare")]
         + [REPO / "text2bpmn/cases" / case / "reference.bpmn" for case in ("loan", "goods_dispatch", "healthcare")])
B = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _flows(bpmn):
    return len(list(ET.parse(bpmn).getroot().iter(f"{B}sequenceFlow")))


@pytest.mark.parametrize("bpmn", FILES, ids=lambda p: f"{p.parent.name}-{p.stem}")
def test_no_line_through_a_box_and_no_overlapping_names(bpmn, tmp_path):
    svg = tmp_path / "figure.svg"
    svg.write_text(render(bpmn), encoding="utf-8")
    report = check(svg, use_inkscape=False)      # font-metric boxes: stricter than glyphs
    assert report["edges"] == _flows(bpmn)
    for key in ("crossings", "own_box", "bad_ends", "label_overlaps", "flow_names_far_from_line"):
        assert report[key] == 0, report["details"]


def test_same_file_same_drawing_whatever_the_hash_seed():
    bpmn = REPO / "runs/final-3/cases/goods_dispatch/model.bpmn"
    code = f"import sys; from text2bpmn.render import render; sys.stdout.write(render({str(bpmn)!r}))"
    outputs = {subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                              env={**os.environ, "PYTHONHASHSEED": seed}, check=True).stdout
               for seed in ("1", "2", "12345")}
    assert len(outputs) == 1 and outputs.pop() == render(bpmn)


def test_loan_rejection_goes_around_sent(tmp_path):
    """The case that prompted the router: in the stored layout the line from
    'Rejected the application' to the join runs straight through 'Sent'."""
    bpmn = REPO / "runs/final-3/cases/loan/model.bpmn"
    svg = render(bpmn)
    sent = re.search(r"<rect data-kind='task' data-bpmn=\"Activity_c7a980a9\" x='([\d.]+)' y='([\d.]+)' "
                     r"width='([\d.]+)' height='([\d.]+)'", svg)
    x, y, w, h = (float(v) for v in sent.groups())
    line = re.search(r"data-source=\"Activity_a4b57b3a\" data-target=\"Gateway_join_1\" points='([^']+)'", svg)
    points = [tuple(float(v) for v in p.split(",")) for p in line.group(1).split()]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        assert not (min(x1, x2) < x + w and x < max(x1, x2) and min(y1, y2) < y + h and y < max(y1, y2))
    # ... while the waypoints stored in the file do cross it
    stored = tmp_path / "stored.svg"
    stored.write_text(svg.replace(line.group(1), "955.00,300.00 1180.00,300.00"), encoding="utf-8")
    assert check(stored, use_inkscape=False)["crossings"] == 1


def test_check_counts_a_name_on_a_line_and_on_a_box(tmp_path):
    svg = render(REPO / "runs/final-3/cases/loan/model.bpmn")
    # move the 'Loan application' flow name onto the 'Approved a loan application' task
    moved = re.sub(r"(data-for=\"Flow_9\"><text x=')[\d.]+(' y=')[\d.]+", r"\g<1>305\g<2>60", svg)
    assert moved != svg
    path = tmp_path / "moved.svg"
    path.write_text(moved, encoding="utf-8")
    report = check(path, use_inkscape=False)
    assert report["label_box"] >= 1 and report["label_overlaps"] >= 1
