# tests/research/test_lifecycle_stabilization.py
"""AEGIS · Sprint M Phase A · executable spec.

Each audit is a spec that fails when the state machine drifts.
Run: pytest tests/research/test_lifecycle_stabilization.py -v
"""
from __future__ import annotations

from backend.research.lifecycle_stabilization import (
    classify_opportunity_state,
    audit_a1_position_id_immutable,
    audit_a2_one_active_per_ticker_runner,
    audit_a3_new_existing_reentry_classifier,
    audit_a5_no_closed_as_new,
    compute, summary_line, render_markdown,
    VALID_STATES,
)


# ═════════════════════════════════════════════════════════════════
# A3 · NEW / EXISTING / RE-ENTRY classifier · pure unit tests
# ═════════════════════════════════════════════════════════════════
class TestA3Classifier:

    def test_first_time_ticker_is_new(self):
        assert classify_opportunity_state(
            ticker="TCS", market="india", runner="R2",
            rec_date="2026-08-25", asof="2026-08-25",
            registry_history=[],
        ) == "NEW"

    def test_currently_active_is_existing(self):
        history = [{"ticker": "TCS", "runner": "R2", "status": "ACTIVE",
                    "created_date": "2026-08-10", "closed_date": None}]
        assert classify_opportunity_state(
            ticker="TCS", market="india", runner="R2",
            rec_date="2026-08-25", asof="2026-08-25",
            registry_history=history,
        ) == "EXISTING"

    def test_previously_closed_today_new_rec_is_reentry(self):
        history = [{"ticker": "LUPIN", "runner": "R2", "status": "CLOSED",
                    "created_date": "2026-08-05",
                    "closed_date": "2026-08-18"}]
        assert classify_opportunity_state(
            ticker="LUPIN", market="india", runner="R2",
            rec_date="2026-08-25", asof="2026-08-25",
            registry_history=history,
        ) == "RE-ENTRY"

    def test_previously_closed_old_rec_is_closed(self):
        history = [{"ticker": "LUPIN", "runner": "R2", "status": "CLOSED",
                    "created_date": "2026-08-05",
                    "closed_date": "2026-08-18"}]
        assert classify_opportunity_state(
            ticker="LUPIN", market="india", runner="R2",
            rec_date="2026-08-20", asof="2026-08-25",
            registry_history=history,
        ) == "CLOSED"

    def test_different_runner_ticker_treated_independently(self):
        # LUPIN R1 active · but classifying R2 · should be NEW (different runner)
        history = [{"ticker": "LUPIN", "runner": "R1", "status": "ACTIVE",
                    "created_date": "2026-08-10", "closed_date": None}]
        assert classify_opportunity_state(
            ticker="LUPIN", market="india", runner="R2",
            rec_date="2026-08-25", asof="2026-08-25",
            registry_history=history,
        ) == "NEW"


# ═════════════════════════════════════════════════════════════════
# Fake Registry + audits · use synthetic data
# ═════════════════════════════════════════════════════════════════
class _FakeOpp:
    def __init__(self, ticker, runner, market, status,
                 created_date, closed_date=None, opp_id=None):
        self.ticker = ticker
        self.runner = runner
        self.market = market
        self.status = status
        self.created_date = created_date
        self.closed_date = closed_date
        self.opportunity_id = opp_id or f"{ticker}_{runner}_{created_date}"

    def is_active(self):
        return self.status in ("NEW", "ACTIVE", "ACTIVE+", "HOLD")


def _patch_registry(monkeypatch, entries):
    """Monkey-patch opportunity_registry.load_all to return synthetic data."""
    def fake_load_all(_root):
        return {"synthetic": entries}
    monkeypatch.setattr(
        "backend.research.opportunity_registry.load_all",
        fake_load_all)


class TestA1PositionIdImmutable:

    def test_unique_ids_pass(self, tmp_path, monkeypatch):
        entries = [
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-10",
                     opp_id="TCS_R2_1"),
            _FakeOpp("LUPIN","R2","india","CLOSED","2026-08-01",
                     "2026-08-15", opp_id="LUPIN_R2_1"),
        ]
        _patch_registry(monkeypatch, entries)
        r = audit_a1_position_id_immutable(tmp_path, "india")
        assert r.status == "PASS"

    def test_reused_id_fails(self, tmp_path, monkeypatch):
        entries = [
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-10",
                     opp_id="DUP-ID"),
            _FakeOpp("LUPIN","R2","india","NEW","2026-08-25",
                     opp_id="DUP-ID"),   # SAME ID · violation
        ]
        _patch_registry(monkeypatch, entries)
        r = audit_a1_position_id_immutable(tmp_path, "india")
        assert r.status == "FAIL"
        assert len(r.violations) == 1


class TestA2OneActivePerTickerRunner:

    def test_no_dup_pass(self, tmp_path, monkeypatch):
        entries = [
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-10"),
            _FakeOpp("TCS","R1","india","ACTIVE","2026-08-11"),   # different runner OK
            _FakeOpp("LUPIN","R2","india","CLOSED","2026-08-01","2026-08-15"),
        ]
        _patch_registry(monkeypatch, entries)
        r = audit_a2_one_active_per_ticker_runner(tmp_path, "india")
        assert r.status == "PASS"

    def test_dup_active_fails(self, tmp_path, monkeypatch):
        entries = [
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-10"),
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-25"),  # SAME (ticker,runner) both active
        ]
        _patch_registry(monkeypatch, entries)
        r = audit_a2_one_active_per_ticker_runner(tmp_path, "india")
        assert r.status == "FAIL"
        assert r.violations[0]["ticker"] == "TCS"


class TestA5NoClosedAsNew:

    def test_no_reuse_pass(self, tmp_path, monkeypatch):
        entries = [
            _FakeOpp("LUPIN","R2","india","CLOSED","2026-08-05",
                     "2026-08-15", opp_id="LUPIN-1"),
            _FakeOpp("LUPIN","R2","india","NEW","2026-08-25",
                     opp_id="LUPIN-2"),   # different ID = legitimate re-entry
        ]
        _patch_registry(monkeypatch, entries)
        r = audit_a5_no_closed_as_new(tmp_path, "india")
        assert r.status == "PASS"

    def test_reuse_fails(self, tmp_path, monkeypatch):
        entries = [
            _FakeOpp("LUPIN","R2","india","CLOSED","2026-08-05",
                     "2026-08-15", opp_id="LUPIN-1"),
            _FakeOpp("LUPIN","R2","india","NEW","2026-08-25",
                     opp_id="LUPIN-1"),   # SAME ID reused = LOCK 2 violation
        ]
        _patch_registry(monkeypatch, entries)
        r = audit_a5_no_closed_as_new(tmp_path, "india")
        assert r.status == "FAIL"


class TestCompute:

    def test_compute_returns_10_audits(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [])
        rep = compute(tmp_path, "india")
        assert rep.n_audits == 10
        assert len(rep.audits) == 10
        # Every audit has a code A1..A10
        codes = [a.code for a in rep.audits]
        assert set(codes) == {f"A{i}" for i in range(1, 11)}

    def test_verdict_ranks_worst_up(self, tmp_path, monkeypatch):
        # Empty registry · A2/A5/A3 pass · file-audits WARN · verdict = WARN
        _patch_registry(monkeypatch, [])
        rep = compute(tmp_path, "india")
        assert rep.verdict in ("PASS", "WARN")   # can't FAIL on empty registry

    def test_summary_line(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [])
        rep = compute(tmp_path, "india")
        s = summary_line(rep)
        assert "lifecycle_stabilization" in s
        assert "verdict=" in s

    def test_render_markdown(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [])
        rep = compute(tmp_path, "india")
        md = render_markdown(rep)
        assert "Sprint M Phase A" in md
        assert "A1" in md and "A10" in md


class TestValidStates:

    def test_locked_states_present(self):
        # LOCK 2 · CEO tightened 2026-08-25 v2 · canonical = 4 states.
        # EXIT is the ONE terminal word · CLOSED is LEGACY only.
        assert "NEW" in VALID_STATES
        assert "ACTIVE" in VALID_STATES
        assert "ACTIVE+" in VALID_STATES
        assert "EXIT" in VALID_STATES
        assert "CLOSED" not in VALID_STATES  # canonicalized to EXIT

    def test_forbidden_states_not_present(self):
        # LOCK 2 · these must NOT be treated as separate lifecycle states
        # (they exist only as decision modifiers on ACTIVE rows)
        assert "PROTECT" not in VALID_STATES
        assert "REVIEW" not in VALID_STATES
        assert "TRAIL" not in VALID_STATES
        assert "TAKE_PROFIT" not in VALID_STATES
