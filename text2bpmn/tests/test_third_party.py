"""Third-party files kept in the repository are the ones their notices name."""
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CAMUNDA = "https://github.com/camunda/bpmn-for-research"
CAMUNDA_REFERENCE_SHA256 = "bae9ed647ee86d46a8389d1099d06857aa0aee12181cb01ae4ac449e8b198436"


def test_the_goods_dispatch_reference_is_camundas_file_unchanged():
    """Byte-identical to BPMN for Research/English/01-Dispatch-of-goods/03-Solution/
    Dispatch-of-goods.bpmn at commit 1416f6f2 (third_party/camunda/NOTICE)."""
    data = (REPO / "text2bpmn/cases/goods_dispatch/reference.bpmn").read_bytes()
    assert hashlib.sha256(data).hexdigest() == CAMUNDA_REFERENCE_SHA256


def test_the_camunda_notice_keeps_the_link_and_the_terms():
    notice = (REPO / "third_party/camunda/NOTICE").read_text(encoding="utf-8")
    assert CAMUNDA in notice and CAMUNDA_REFERENCE_SHA256 in notice
    assert "academic and research" in notice and "Commercial use" in notice
    for path in ("text2bpmn/cases/goods_dispatch/reference.bpmn", "text2bpmn/cases/goods_dispatch/input.txt"):
        assert path in notice and (REPO / path).exists()
    third_party = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert CAMUNDA in third_party and "third_party/camunda/NOTICE" in third_party


def test_the_fetched_third_party_files_stay_out_of_git():
    """BBO (GPL-3.0) and Neuberger et al.'s files (no licence) are fetched,
    pinned and checked, never committed (THIRD_PARTY_NOTICES.md)."""
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("/BPMNbasedOntologyV1_2.owl", "text2bpmn/checks/shacl/", "text2bpmn/baselines/neuberger/"):
        assert pattern in ignored, pattern
