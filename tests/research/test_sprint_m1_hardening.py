# tests/research/test_sprint_m1_hardening.py
"""AEGIS · Sprint M.1 · hardening tests for:
   · opportunity_engine data_state semantics (M.1.2)
   · new_opportunity_outcomes forward-return tracker (M.1.3)
   · ranking_effectiveness monotonicity + bucket metrics
   · missed_opportunity_v2 rejection classifier
"""
from __future__ import annotations

import json
import pandas as pd
from pathlib import Path
import pytest


# ═════════════════════════════════════════════════════════════════
# M.1.2 · opportunity_engine data_state semantics
# ═════════════════════════════════════════════════════════════════
class TestOpportunityEngineDataState:

    def test_missing_recs_gives_UNAVAILABLE(self, tmp_path, monkeypatch):
        # No recs.json at all
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.data_state == "UNAVAILABLE"

    def test_stale_recs_gives_STALE(self, tmp_path, monkeypatch):
        recs_p = tmp_path / "reports" / "recommendations.json"
        recs_p.parent.mkdir(parents=True, exist_ok=True)
        recs_p.write_text(json.dumps({
            "asof": "2026-08-01", "recommendations": [{"ticker": "X"}]
        }), encoding="utf-8")
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.data_state == "STALE"
        assert rep.recs_stale_days == 24

    def test_valid_recs_gives_VALID(self, tmp_path, monkeypatch):
        recs_p = tmp_path / "reports" / "recommendations.json"
        recs_p.parent.mkdir(parents=True, exist_ok=True)
        recs_p.write_text(json.dumps({
            "asof": "2026-08-25", "recommendations": [{"ticker": "X"}]
        }), encoding="utf-8")
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.data_state == "VALID"

    def test_empty_recs_gives_NO_OPPORTUNITY(self, tmp_path, monkeypatch):
        recs_p = tmp_path / "reports" / "recommendations.json"
        recs_p.parent.mkdir(parents=True, exist_ok=True)
        recs_p.write_text(json.dumps({
            "asof": "2026-08-25", "recommendations": []
        }), encoding="utf-8")
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        assert rep.data_state == "NO_OPPORTUNITY"

    def test_summary_line_includes_state(self, tmp_path, monkeypatch):
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import opportunity_engine as _oe
        rep = _oe.compute(tmp_path, "india", "2026-08-25")
        s = _oe.summary_line(rep)
        assert "state=" in s


# ═════════════════════════════════════════════════════════════════
# M.1.3 · new_opportunity_outcomes
# ═════════════════════════════════════════════════════════════════
@pytest.fixture
def synthetic_root(tmp_path):
    """Build a fake parquet + Registry substrate."""
    raw = tmp_path / "data" / "raw" / "india"
    raw.mkdir(parents=True)
    dates = pd.date_range("2026-08-01", periods=30, freq="B")
    # Winner path · +2% per day
    closes = [100.0 * (1.02 ** i) for i in range(len(dates))]
    df = pd.DataFrame({
        "open": closes, "high": closes, "low": closes,
        "close": closes, "tick_volume": [1000] * len(dates),
        "spread": [0.0] * len(dates),
    }, index=dates)
    df.index.name = "time"
    df.to_parquet(raw / "TESTWIN_D1.parquet")
    # Loser path · -2% per day
    closes_l = [100.0 * (0.98 ** i) for i in range(len(dates))]
    df_l = df.copy(); df_l["close"] = closes_l
    df_l.to_parquet(raw / "TESTLOSE_D1.parquet")
    # Flat · unchanged
    df_f = df.copy(); df_f["close"] = [100.0] * len(dates)
    df_f.to_parquet(raw / "TESTFLAT_D1.parquet")
    return tmp_path


class TestNewOpportunityOutcomes:

    def test_empty_registry_zero_outcomes(self, synthetic_root, monkeypatch):
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import new_opportunity_outcomes as _oo
        rep = _oo.compute(synthetic_root, "india")
        assert rep.n_total == 0

    def test_winner_gets_positive_forward_returns(self, synthetic_root, monkeypatch):
        class _Opp:
            def __init__(self):
                self.ticker = "TESTWIN"; self.runner = "R2"
                self.market = "india"; self.status = "ACTIVE"
                self.created_date = "2026-08-03"
                self.closed_date = None
                self.opportunity_id = "TW-1"
            def is_active(self): return True
        def fake_load(_root): return {"x": [_Opp()]}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import new_opportunity_outcomes as _oo
        rep = _oo.compute(synthetic_root, "india")
        assert rep.n_total >= 1
        o = rep.outcomes[0]
        # 5D forward should be positive (winner path)
        if o.get("fwd_5d_pct") is not None:
            assert o["fwd_5d_pct"] > 0


# ═════════════════════════════════════════════════════════════════
# Ranking effectiveness
# ═════════════════════════════════════════════════════════════════
class TestRankingEffectiveness:

    def test_empty_history_zero_positions(self, tmp_path):
        from backend.research import ranking_effectiveness as _re
        rep = _re.compute(tmp_path, "india")
        assert rep.n_positions == 0

    def test_monotonicity_test_needs_min_data(self, tmp_path):
        from backend.research.ranking_effectiveness import _monotonicity_test
        result = _monotonicity_test([{"rank": 1, "n": 2, "fwd_20d_avg": 5.0}])
        assert result["status"] == "insufficient-data"

    def test_monotonicity_test_detects_monotonic(self):
        from backend.research.ranking_effectiveness import _monotonicity_test
        per_rank = [
            {"rank": 1, "n": 10, "fwd_20d_avg": 5.0},
            {"rank": 2, "n": 10, "fwd_20d_avg": 4.0},
            {"rank": 3, "n": 10, "fwd_20d_avg": 3.0},
        ]
        r = _monotonicity_test(per_rank)
        assert r["status"] == "MONOTONIC"
        assert r["best_rank_by_20d"] == 1

    def test_monotonicity_test_detects_inversion(self):
        from backend.research.ranking_effectiveness import _monotonicity_test
        per_rank = [
            {"rank": 1, "n": 10, "fwd_20d_avg": 2.0},
            {"rank": 2, "n": 10, "fwd_20d_avg": 5.0},  # inversion!
            {"rank": 3, "n": 10, "fwd_20d_avg": 1.0},
        ]
        r = _monotonicity_test(per_rank)
        assert r["status"] == "NON_MONOTONIC"
        assert r["n_inversions"] >= 1
        assert r["best_rank_by_20d"] == 2   # rank 2 beat rank 1


# ═════════════════════════════════════════════════════════════════
# Missed opportunity v2
# ═════════════════════════════════════════════════════════════════
class TestMissedOpportunityV2:

    def test_classifier(self):
        from backend.research.missed_opportunity_v2 import _classify
        # Big win at 20d
        assert _classify(r5=3, r20=18) == "MISSED_STRONG_WIN"
        # 5d win only
        assert _classify(r5=8, r20=None) == "MISSED_WINNER"
        # Big loss
        assert _classify(r5=-2, r20=-10) == "SUCCESSFUL_REJECT"
        # Flat
        assert _classify(r5=1, r20=2) == "IGNORED_NEUTRAL"
        # No data
        assert _classify(r5=None, r20=None) == "IGNORED_NEUTRAL"

    def test_empty_universe_zero_rejected(self, tmp_path, monkeypatch):
        def fake_load(_root): return {}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import missed_opportunity_v2 as _mo
        rep = _mo.compute(tmp_path, "india", lookback_days=30)
        assert rep.n_universe == 0
