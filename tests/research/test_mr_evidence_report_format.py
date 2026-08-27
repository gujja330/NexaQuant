"""CEO 2026-08-27 · compact evidence report format tests."""
from backend.research.mr_evidence_report import _operator_status


def test_operator_status_shadow_when_accumulating():
    assert _operator_status("NEED_DATA") == "SHADOW"
    assert _operator_status("ACCUMULATING") == "SHADOW"


def test_operator_status_ready_when_at_target():
    assert _operator_status("READY_TO_JUDGE") == "READY"


def test_operator_status_promotable_when_passed():
    assert _operator_status("PASSED") == "PROMOTABLE"


def test_operator_status_rejected_when_failed():
    assert _operator_status("FAILED") == "REJECTED"


def test_operator_status_defaults_to_shadow():
    assert _operator_status("UNKNOWN") == "SHADOW"
