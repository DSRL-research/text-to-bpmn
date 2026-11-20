"""A check's report names no machine: the paths it records are relative to the
repository, or to the home directory, never absolute."""
from pathlib import Path

from text2bpmn.checks.common import REPO, portable, provenance


def test_paths_in_the_repository_become_relative():
    assert portable(str(REPO / "text2bpmn/checks/schemas/BPMN20.xsd")) == "text2bpmn/checks/schemas/BPMN20.xsd"
    assert portable(REPO / "BPMNbasedOntologyV1_2.owl") == "BPMNbasedOntologyV1_2.owl"


def test_paths_elsewhere_under_home_keep_only_the_part_below_it():
    home = Path("/somewhere/user")
    assert portable("/somewhere/user/.venvs/env/bin/python", repo=Path("/elsewhere"), home=home) \
        == "~/.venvs/env/bin/python"
    # the repository is checked first, so a repository inside the home directory is relative
    assert portable("/somewhere/user/repo/a.owl", repo=home / "repo", home=home) == "a.owl"


def test_everything_else_is_left_as_it_is():
    assert portable("runs/final-3/cases") == "runs/final-3/cases"
    assert portable("/usr/share/x.xsd", repo=Path("/r"), home=Path("/h")) == "/usr/share/x.xsd"
    assert portable(3) == 3 and portable(None) is None


def test_the_provenance_record_walks_lists_and_dicts():
    record = provenance(schema=str(REPO / "s.xsd"), folders=[str(REPO / "runs/a"), "runs/b"],
                        references={"x": str(REPO / "r.bpmn")})
    assert record["schema"] == "s.xsd"
    assert record["folders"] == ["runs/a", "runs/b"]
    assert record["references"] == {"x": "r.bpmn"}
    assert "run_at" in record and "code" in record


def test_cq_compare_reads_pilots_and_release_runs():
    """Pilots keep a case in <pilot>/case-<case>/, the release runs in
    <experiment>/<case>/ (runs/final-3/cases/loan)."""
    from text2bpmn.checks.cq_compare import BBO_SHA256, case_folder
    from text2bpmn.checks.fetch_bbo import FILES

    assert case_folder("runs/pilot", "loan") == Path("runs/pilot/case-loan")
    assert case_folder("runs/final-3/cases", "loan", "release") == Path("runs/final-3/cases/loan")
    assert (REPO / case_folder("runs/final-3/cases", "loan", "release") / "ontology.owl").exists()
    assert BBO_SHA256 == FILES["BPMNbasedOntologyV1_2.owl"][1]
