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


# ─────────────────────────────────────────────────────────────
# CEO 2026-08-27 · I28 regression tests (EA delisting root-cause)
#
# Bug reproduced: mr_orphan_closer previously used ambient asof as
# closed_date · fabricating an exit_date for tickers with NO market
# data on asof. Real example · EA delisted 2026-08-10 · closed with
# closed_date=2026-08-26 · I28 validator correctly refused it.
#
# Correct behavior: closed_date = last-known-evidence date
#   priority: ls (last aegis_history date)
#          →  cd (created_date)
#          →  asof_iso (only if both missing)
# ─────────────────────────────────────────────────────────────


def _bootstrap_orphan_registry(tmp_path, ticker, runner, created_date):
    """Write a minimal Registry with one ACTIVE opportunity."""
    from backend.research.opportunity_registry import make_opportunity_id
    p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    pid = make_opportunity_id("usa", runner, ticker, created_date)
    row = {
        "opportunity_id": pid, "market": "usa", "runner": runner,
        "ticker": ticker, "created_date": created_date,
        "initial_signal": "BUY", "initial_rank": 1,
        "initial_score": 0.85, "status": "ACTIVE",
        "closed_date": "", "closed_reason": "",
        "last_seen_date": created_date, "ts_utc": "2026-08-11T00:00:00+00:00",
    }
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return pid


def _write_empty_canonical(tmp_path):
    """Empty canonical INVESTMENT_ACTIVE so orphan is NOT in canonical."""
    p = tmp_path / "reports" / "context" / "portfolio_canonical_usa.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"investment_active": []}), encoding="utf-8")


def test_orphan_close_uses_last_seen_not_asof(tmp_path, monkeypatch):
    """CEO 2026-08-27 · I28 EA regression. When a ticker has a
    last_seen_in_history value (e.g., EA last in history on 2026-08-10)
    and is orphaned by asof=2026-08-26, the closed_date MUST be
    2026-08-10 (last evidence), NOT 2026-08-26 (fabricated asof)."""
    from backend.research import mr_orphan_closer as m
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    _write_empty_canonical(tmp_path)
    monkeypatch.setattr(m, "_last_seen_in_history",
                        lambda root, mkt, days: {("EA", "R2"): "2026-08-10"})
    recs = m.close_orphans(tmp_path, "usa", asof="2026-08-26",
                            dry_run=False, stale_days=10)
    closed = [r for r in recs if r.action == "CLOSED"]
    assert len(closed) == 1
    assert closed[0].ticker == "EA"
    reg = oreg.load_all(tmp_path)
    row = None
    for opps in reg.values():
        for o in opps:
            if o.opportunity_id == pid: row = o
    assert row is not None
    assert row.status == "CLOSED"
    assert row.closed_reason == "ORPHAN_AUTO_CLOSE"
    # THE FIX: closed_date is last-known-evidence, NOT ambient asof
    assert row.closed_date == "2026-08-10", \
        f"closed_date should be last-known-evidence 2026-08-10 · got {row.closed_date}"
    assert row.closed_date != "2026-08-26", \
        "closed_date must NEVER be the ambient asof for an orphan"


def test_orphan_close_falls_back_to_created_date_when_no_history(
        tmp_path, monkeypatch):
    """When last_seen_in_history is missing, closed_date falls back to
    created_date · never to ambient asof."""
    from backend.research import mr_orphan_closer as m
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "ZZZ", "R1", "2026-08-05")
    _write_empty_canonical(tmp_path)
    monkeypatch.setattr(m, "_last_seen_in_history",
                        lambda root, mkt, days: {})
    recs = m.close_orphans(tmp_path, "usa", asof="2026-08-26",
                            dry_run=False, stale_days=10)
    closed = [r for r in recs if r.action == "CLOSED"]
    assert len(closed) == 1
    reg = oreg.load_all(tmp_path)
    row = next(o for opps in reg.values() for o in opps
                if o.opportunity_id == pid)
    assert row.closed_date == "2026-08-05", \
        f"closed_date should be created_date 2026-08-05 · got {row.closed_date}"


def test_orphan_close_enforces_closed_date_ge_created_date(
        tmp_path, monkeypatch):
    """CI run 33074829157 · Row 528 · EA · exit=2026-08-10 · entry=2026-08-11 ·
    I28 exit_before_entry. The earlier fix (ls or cd) took ls when ls < cd ·
    that violated the invariant closed_date >= created_date. Regression:
    when last_seen_in_history < created_date, closed_date MUST fall back to
    created_date (a same-day open+close · the position was born but the
    ticker had no market data on the birth date)."""
    from backend.research import mr_orphan_closer as m
    from backend.research import opportunity_registry as oreg
    # EA-like setup: cd (birth) = Aug 11 · ls (last real data) = Aug 10
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-11")
    _write_empty_canonical(tmp_path)
    monkeypatch.setattr(m, "_last_seen_in_history",
                        lambda root, mkt, days: {("EA", "R2"): "2026-08-10"})
    recs = m.close_orphans(tmp_path, "usa", asof="2026-08-26",
                            dry_run=False, stale_days=10)
    closed = [r for r in recs if r.action == "CLOSED"]
    assert len(closed) == 1
    reg = oreg.load_all(tmp_path)
    row = next(o for opps in reg.values() for o in opps
                if o.opportunity_id == pid)
    # THE FIX: closed_date >= created_date · never before birth
    assert row.closed_date == "2026-08-11", \
        (f"closed_date should be max(ls=Aug 10, cd=Aug 11) = Aug 11 · "
         f"got {row.closed_date} · I28 exit_before_entry would fire in CI")
    assert row.closed_date >= row.created_date, \
        "invariant violated: closed_date must be >= created_date"


def test_orphan_close_does_not_fabricate_dates_after_evidence(
        tmp_path, monkeypatch):
    """Property: closed_date <= max(created_date, last_seen_in_history).
    Guarantees no fabricated exit_date after ticker's last evidence."""
    from backend.research import mr_orphan_closer as m
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "DELISTED", "R2", "2026-07-15")
    _write_empty_canonical(tmp_path)
    monkeypatch.setattr(m, "_last_seen_in_history",
                        lambda root, mkt, days: {("DELISTED", "R2"): "2026-08-05"})
    recs = m.close_orphans(tmp_path, "usa", asof="2026-08-26",
                            dry_run=False, stale_days=10)
    assert any(r.action == "CLOSED" for r in recs)
    reg = oreg.load_all(tmp_path)
    row = next(o for opps in reg.values() for o in opps
                if o.opportunity_id == pid)
    assert row.closed_date <= "2026-08-05", \
        (f"closed_date {row.closed_date} must be <= last-evidence 2026-08-05 · "
         "no fabrication after ticker's last known trading session")


def test_orphan_close_dry_run_still_reports_correct_closed_date(
        tmp_path, monkeypatch):
    """Dry-run must show the LEGITIMATE closed_date in its report row ·
    the operator uses this to preview what would happen."""
    from backend.research import mr_orphan_closer as m
    _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    _write_empty_canonical(tmp_path)
    monkeypatch.setattr(m, "_last_seen_in_history",
                        lambda root, mkt, days: {("EA", "R2"): "2026-08-10"})
    recs = m.close_orphans(tmp_path, "usa", asof="2026-08-26",
                            dry_run=True, stale_days=10)
    would_close = [r for r in recs if r.action == "WOULD_CLOSE"]
    assert len(would_close) == 1
    # The reason string exposes the target closed_date
    assert "closed_date=max(last-known,cd)=2026-08-10" in would_close[0].reason


# ─────────────────────────────────────────────────────────────
# CEO 2026-08-27 · canonical-repair API tests
# Repairs an already-CLOSED Registry event without decision-logic
# mutation. Append-only. Idempotent. Requires audit attribution.
# ─────────────────────────────────────────────────────────────


def test_apply_canonical_repair_overrides_closed_date(tmp_path):
    """The canonical repair API updates closed_date on an already-CLOSED
    Registry event AND appends a new event with the corrected value AND
    preserves the original event on disk (append-only)."""
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    # First close with wrong (asof-style) closed_date
    oreg.close(tmp_path, pid, "2026-08-26",
                reason="ORPHAN_AUTO_CLOSE (wrong asof)")
    reg = oreg.load_all(tmp_path)
    ea = next(o for opps in reg.values() for o in opps
                if o.opportunity_id == pid)
    assert ea.closed_date == "2026-08-26"
    # Apply canonical repair
    result = oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10",
        closed_reason="canonical repair",
        authoritative_source="yfinance",
        approval="CEO test")
    assert result is not None
    reg2 = oreg.load_all(tmp_path)
    ea2 = next(o for opps in reg2.values() for o in opps
                if o.opportunity_id == pid)
    assert ea2.closed_date == "2026-08-10"
    # Append-only preservation
    import json
    events_2026_08_26 = 0
    events_2026_08_10 = 0
    with open(tmp_path / "reports/research/opportunity_registry.jsonl") as f:
        for ln in f:
            if not ln.strip(): continue
            r = json.loads(ln)
            if r.get("opportunity_id") != pid: continue
            if r.get("closed_date") == "2026-08-26": events_2026_08_26 += 1
            if r.get("closed_date") == "2026-08-10": events_2026_08_10 += 1
    assert events_2026_08_26 >= 1, \
        "original wrong-closed_date event was silently overwritten"
    assert events_2026_08_10 == 1, "canonical repair event missing"


def test_apply_canonical_repair_is_idempotent(tmp_path):
    """Rerunning the same canonical repair with identical values is a
    no-op · does not append a duplicate event."""
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    oreg.close(tmp_path, pid, "2026-08-26", reason="wrong")
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="canonical",
        authoritative_source="yf", approval="test")
    # Count events with closed_date=2026-08-10
    import json
    def count():
        n = 0
        with open(tmp_path / "reports/research/opportunity_registry.jsonl") as f:
            for ln in f:
                if not ln.strip(): continue
                r = json.loads(ln)
                if r.get("opportunity_id") == pid and \
                        r.get("closed_date") == "2026-08-10":
                    n += 1
        return n
    assert count() == 1
    # Repeat
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="canonical",
        authoritative_source="yf", approval="test")
    assert count() == 1, "canonical repair was NOT idempotent"


def test_apply_canonical_repair_requires_attribution(tmp_path):
    """Canonical repair with no authoritative_source or approval is
    rejected · silent edits are not permitted."""
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    oreg.close(tmp_path, pid, "2026-08-26", reason="wrong")
    r1 = oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="repair",
        authoritative_source="", approval="")
    assert r1 is None
    # With attribution · succeeds
    r2 = oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="repair",
        authoritative_source="yf", approval="CEO")
    assert r2 is not None


def test_apply_canonical_repair_only_operates_on_closed_status(tmp_path):
    """Canonical repair refuses to touch ACTIVE positions · status
    transitions require close()/reject() (decision-logic paths).
    Repair is for date-field corrections on already-terminal records."""
    from backend.research import opportunity_registry as oreg
    _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    pid = f"USA-R2-EA-20260801-{'a'*6}"
    # Import correct pid
    from backend.research.opportunity_registry import make_opportunity_id
    pid = make_opportunity_id("usa", "R2", "EA", "2026-08-01")
    r = oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="x",
        authoritative_source="yf", approval="CEO")
    assert r is None, "repair should refuse ACTIVE opportunity"


def test_apply_canonical_repair_preserves_prior_created_date(tmp_path):
    """The canonical repair path never touches created_date · the
    immutable-created_date rule of the Registry is preserved."""
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    oreg.close(tmp_path, pid, "2026-08-26", reason="wrong")
    reg = oreg.load_all(tmp_path)
    before_cd = next(o for opps in reg.values() for o in opps
                        if o.opportunity_id == pid).created_date
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="repair",
        authoritative_source="yf", approval="CEO")
    reg2 = oreg.load_all(tmp_path)
    after_cd = next(o for opps in reg2.values() for o in opps
                        if o.opportunity_id == pid).created_date
    assert before_cd == after_cd == "2026-08-01"


def test_exit_history_synthesis_uses_repaired_closed_date(tmp_path):
    """Simulates the Registry-sync logic in Exit History emission:
    when a pid has both an original event (closed_date=X) and a
    canonical-repair event (closed_date=Y) with a later ts_utc,
    Registry loader returns Y · Exit History synthesizes an exit_date=Y
    row · I28 validator finds the ticker's parquet close on Y (a real
    trading session) · I28 PASSES.
    This is the exact defect class from CI run 33069236589 (EA)."""
    from backend.research import opportunity_registry as oreg
    pid = _bootstrap_orphan_registry(tmp_path, "EA", "R2", "2026-08-01")
    oreg.close(tmp_path, pid, "2026-08-26",
                reason="ORPHAN_AUTO_CLOSE (buggy asof)")
    # Simulate the exact CI condition
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10",
        closed_reason="ORPHAN_AUTO_CLOSE · CANONICAL_REPAIR",
        authoritative_source="yfinance",
        approval="CEO 2026-08-27")
    # This is what scripts/telegram_command_center_send.py's Registry
    # sync sees at line 3054-3097:
    reg = oreg.load_all(tmp_path)
    exit_history_synthesized = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != "usa": continue
            if o.status != "CLOSED": continue
            if not o.closed_date: continue
            exit_history_synthesized.append({
                "ticker": o.ticker,
                "runner": o.runner,
                "closed_date": o.closed_date,
            })
    ea_rows = [r for r in exit_history_synthesized if r["ticker"] == "EA"]
    assert len(ea_rows) == 1
    # THE FIX: exit_date is the repaired value, not the wrong original
    assert ea_rows[0]["closed_date"] == "2026-08-10", \
        (f"Exit History synthesis should use repaired closed_date=2026-08-10 · "
         f"got {ea_rows[0]['closed_date']} · I28 would still FAIL")
