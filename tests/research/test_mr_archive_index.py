"""Tests for the archive index + 5-way status routing."""
from backend.research.mr_archive_index import (
    _decision_from_status, _group_by_status, STATUS_ORDER,
)


def test_decision_active_shadow():
    assert _decision_from_status("ACTIVE_SHADOW", None) == "PENDING (accumulating)"


def test_decision_superseded_shows_successor():
    d = _decision_from_status("SUPERSEDED_BY", "aegis_e1")
    assert d == "RETIRED (→ aegis_e1)"


def test_decision_archived():
    assert _decision_from_status("ARCHIVED_FOR_LATER", None) == "ARCHIVED"
    assert _decision_from_status("ARCHIVED_LOW_PRIORITY", None) == "ARCHIVED"


def test_decision_passed_and_failed():
    assert _decision_from_status("PASSED", None) == "PROMOTED_CANDIDATE"
    assert _decision_from_status("FAILED", None) == "REJECTED"


def test_decision_data_gap():
    assert _decision_from_status("DATA_GAP", None) == "BLOCKED_ON_DATA"


def test_status_order_has_five_buckets():
    assert set(STATUS_ORDER) == {
        "SUCCESSFUL_PROMOTION_CANDIDATE",
        "PROMISING_NEED_MORE_DATA",
        "FAILED_RETAIN_EVIDENCE",
        "SUPERSEDED_KEEP_HISTORY",
        "DATA_GAP_FIX_DATA",
    }


def test_group_by_status_routes_cards():
    cards = [
        {"status_5way": "PROMISING_NEED_MORE_DATA", "title": "t1"},
        {"status_5way": "FAILED_RETAIN_EVIDENCE", "title": "t2"},
    ]
    g = _group_by_status(cards)
    assert len(g["PROMISING_NEED_MORE_DATA"]) == 1
    assert len(g["FAILED_RETAIN_EVIDENCE"]) == 1
    assert len(g["SUCCESSFUL_PROMOTION_CANDIDATE"]) == 0
