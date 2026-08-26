"""AEGIS · M-R · Orphan closer tests."""
from __future__ import annotations
import json
from pathlib import Path
import pytest


def test_stale_days_default():
    from backend.research import mr_orphan_closer as m
    assert m.STALE_ORPHAN_DAYS == 10


def test_canonical_active_tickers_missing_file(tmp_path):
    from backend.research.mr_orphan_closer import _canonical_active_tickers
    assert _canonical_active_tickers(tmp_path, "india") == set()


def test_canonical_active_tickers_reads_json(tmp_path):
    from backend.research.mr_orphan_closer import _canonical_active_tickers
    p = tmp_path / "reports" / "context" / "portfolio_canonical_india.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "investment_active": [
            {"ticker": "TCS", "runner": "R1"},
            {"ticker": "INFY.NS", "runner": "R2"},
        ]
    }), encoding="utf-8")
    got = _canonical_active_tickers(tmp_path, "india")
    assert got == {("TCS", "R1"), ("INFY", "R2")}


def test_emit_only_under_research(tmp_path):
    from backend.research.mr_orphan_closer import emit
    p = emit(tmp_path, "india", [])
    assert str(p).replace("\\", "/").endswith(
        "reports/research/mr_orphan_closer_india.json")


def test_emit_payload_shape(tmp_path):
    from backend.research.mr_orphan_closer import emit, ClosureRecord, \
        ENGINE_ID, SCHEMA_FINGERPRINT
    records = [ClosureRecord(
        ticker="TCS", runner="R1", position_id="pid1",
        created_date="2026-08-10", age_days=16,
        last_seen_in_history="2026-08-14", action="WOULD_CLOSE",
        reason="orphan test",
    )]
    p = emit(tmp_path, "india", records)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["engine"] == ENGINE_ID
    assert d["schema_fingerprint"] == SCHEMA_FINGERPRINT
    assert d["n_scanned"] == 1
    assert d["action_counts"] == {"WOULD_CLOSE": 1}


def test_summary_line_format():
    from backend.research.mr_orphan_closer import summary_line, ClosureRecord
    records = [
        ClosureRecord("A", "R1", "p1", "2026-08-10", 16, None, "CLOSED", ""),
        ClosureRecord("B", "R2", "p2", "2026-08-10", 16, None, "KEPT", ""),
        ClosureRecord("C", "R2", "p3", "2026-08-10", 16, None, "KEPT", ""),
    ]
    s = summary_line(records)
    assert "mr_orphan_closer" in s
    assert "CLOSED=1" in s
    assert "KEPT=2" in s
