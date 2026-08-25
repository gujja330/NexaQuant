# tests/research/test_sprint_m_phases.py
"""AEGIS · Sprint M · executable spec for Phase B/C/D/E new modules.

Focused tests · one per public function · verifies contract without
requiring live data (uses tmp_path + fake registry patch).
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest


# ═════════════════════════════════════════════════════════════════
# Phase B · Opportunity Engine
# ═════════════════════════════════════════════════════════════════
class _FakeOpp:
    def __init__(self, ticker, runner, market, status, created_date,
                 closed_date=None, opp_id=None):
        self.ticker = ticker; self.runner = runner
        self.market = market; self.status = status
        self.created_date = created_date; self.closed_date = closed_date
        self.opportunity_id = opp_id or f"{ticker}_{runner}_{created_date}"
    def is_active(self):
        return self.status in ("NEW","ACTIVE","ACTIVE+","HOLD")


def _patch_registry(monkeypatch, entries):
    def fake(_root):
        return {"synthetic": entries}
    monkeypatch.setattr(
        "backend.research.opportunity_registry.load_all", fake)


class TestOpportunityEngine:

    def test_no_registry_returns_zero(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [])
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.n_total_today == 0
        assert rep.freshness_ratio == 0.0

    def test_new_ticker_classified_as_new(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [
            _FakeOpp("TCS","R2","india","NEW","2026-08-25"),
        ])
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.n_total_today == 1
        assert rep.n_new == 1
        assert rep.freshness_ratio == 100.0

    def test_existing_active_classified_as_existing(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-10"),
            _FakeOpp("TCS","R2","india","ACTIVE","2026-08-25"),
        ])
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        # Only the 08-25 entry surfaces as "today's opportunity"
        assert rep.n_existing == 1

    def test_r1_r2_discovery_counted_independently(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [
            _FakeOpp("A","R1","india","NEW","2026-08-25"),
            _FakeOpp("B","R2","india","NEW","2026-08-25"),
            _FakeOpp("C","R2","india","NEW","2026-08-25"),
        ])
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.n_r1_new == 1
        assert rep.n_r2_new == 2

    def test_summary_line_readable(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [])
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        s = _oe.summary_line(rep)
        assert "opportunity_engine" in s
        # M.1.2 · summary now always shows "state=" (VALID or otherwise)
        assert "state=" in s


# ═════════════════════════════════════════════════════════════════
# Phase C · Attribution Matrix
# ═════════════════════════════════════════════════════════════════
class TestAttributionMatrix:

    def test_no_positions_empty_report(self, tmp_path, monkeypatch):
        _patch_registry(monkeypatch, [])
        from backend.research import attribution_matrix as _am
        rep = _am.compute(tmp_path, "india", lookback_days=90)
        assert rep.n_positions == 0
        assert rep.runner_matrix == []

    def test_cell_metrics_shape(self):
        from backend.research.attribution_matrix import _cell_metrics
        items = [
            {"pnl_pct": 3.0, "is_win": True, "days_held": 10},
            {"pnl_pct": -2.0, "is_win": False, "days_held": 5},
            {"pnl_pct": 5.0, "is_win": True, "days_held": 15},
        ]
        m = _cell_metrics(items)
        assert m.n == 3
        assert m.n_wins == 2
        assert m.n_losses == 1
        assert m.win_rate_pct > 60
        assert m.confidence == "observation-only"    # N < 20

    def test_confidence_bands(self):
        from backend.research.attribution_matrix import confidence_band
        assert confidence_band(5) == "observation-only"
        assert confidence_band(25) == "directional"
        assert confidence_band(75) == "research-candidate"
        assert confidence_band(150) == "production-candidate"


# ═════════════════════════════════════════════════════════════════
# Phase D · Statistical Guard
# ═════════════════════════════════════════════════════════════════
class TestStatisticalGuard:

    def test_low_n_blocks_ticket(self):
        from backend.research.statistical_guard import assert_ticket_allowed
        with pytest.raises(ValueError, match="observation-only"):
            assert_ticket_allowed(5)
        with pytest.raises(ValueError, match="observation-only"):
            assert_ticket_allowed(19)

    def test_n_20_allows_ticket(self):
        from backend.research.statistical_guard import assert_ticket_allowed
        assert_ticket_allowed(20)   # no raise
        assert_ticket_allowed(99)

    def test_production_requires_n_100(self):
        from backend.research.statistical_guard import assert_production_ready
        with pytest.raises(ValueError):
            assert_production_ready(50)
        assert_production_ready(100)

    def test_classify_n_bands(self):
        from backend.research.statistical_guard import classify_n
        assert classify_n(5).band == "observation-only"
        assert classify_n(20).band == "directional"
        assert classify_n(50).band == "research-candidate"
        assert classify_n(150).band == "production-candidate"


# ═════════════════════════════════════════════════════════════════
# Phase D · Research Ticket
# ═════════════════════════════════════════════════════════════════
class TestResearchTicket:

    def test_low_n_blocks_filing(self, tmp_path):
        from backend.research.research_ticket import file_ticket
        with pytest.raises(ValueError):
            file_ticket(
                tmp_path,
                finding="test finding",
                evidence={"n": 5, "expectancy_pct": -0.5},
                hypothesis="test",
                required_validation="walk-forward",
                impact_score=5.0,
                market="india",
            )

    def test_valid_ticket_persists(self, tmp_path):
        from backend.research.research_ticket import file_ticket
        t = file_ticket(
            tmp_path,
            finding="Healthcare R2 MidCap has negative expectancy",
            evidence={"n": 30, "expectancy_pct": -1.2, "profit_factor": 0.7},
            hypothesis="Block Healthcare R2 MidCap entries in weak sector regime",
            required_validation="walk-forward N ≥ 20 on last 90 days",
            impact_score=6.5,
            market="india",
            tags=["healthcare","r2","midcap"],
        )
        assert t.id.startswith("RT-")
        assert t.status == "OPEN"
        # File exists on disk
        p = tmp_path / "reports" / "research" / "tickets" / f"{t.id}.md"
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        assert "Healthcare R2 MidCap" in content
        assert "OPEN" in content

    def test_index_populated(self, tmp_path):
        from backend.research.research_ticket import file_ticket, load_top_tickets
        file_ticket(
            tmp_path, finding="A", evidence={"n": 25, "expectancy_pct": -0.8},
            hypothesis="X", required_validation="Y",
            impact_score=3.0, market="india",
        )
        file_ticket(
            tmp_path, finding="B", evidence={"n": 40, "expectancy_pct": -2.5},
            hypothesis="X", required_validation="Y",
            impact_score=9.0, market="india",
        )
        top = load_top_tickets(tmp_path, n=10)
        assert len(top) == 2
        # Ranked by impact desc · B (9.0) before A (3.0)
        assert top[0]["impact_score"] == 9.0

    def test_impact_score_bounds(self, tmp_path):
        from backend.research.research_ticket import file_ticket
        with pytest.raises(ValueError):
            file_ticket(
                tmp_path, finding="X",
                evidence={"n": 30, "expectancy_pct": -1.0},
                hypothesis="Y", required_validation="Z",
                impact_score=11.0,   # out of 0-10
                market="india",
            )


# ═════════════════════════════════════════════════════════════════
# Phase E · Emerging Leader
# ═════════════════════════════════════════════════════════════════
class TestEmergingLeader:

    def test_dimension_scorers_return_dimension_score(self, tmp_path):
        from backend.research.emerging_leader_engine import (
            _score_governance, _score_fundamental, DimensionScore)
        gov = _score_governance(tmp_path, "TESTA", "india")
        assert isinstance(gov, DimensionScore)
        assert gov.dimension == "governance"
        fund = _score_fundamental(tmp_path, "TESTA", "india")
        assert fund.dimension == "fundamental"

    def test_empty_candidates_returns_zero_emerging(self, tmp_path):
        from backend.research.emerging_leader_engine import compute
        rep = compute(tmp_path, "india", candidates=[])
        assert rep.n_candidates_evaluated == 0
        assert rep.n_emerging == 0

    def test_min_dimensions_positive_constant(self):
        from backend.research.emerging_leader_engine import (
            MIN_DIMENSIONS_POSITIVE, QUALITY_DIMENSIONS)
        assert MIN_DIMENSIONS_POSITIVE == 4
        assert len(QUALITY_DIMENSIONS) == 6
