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
#: CEO 2026-11-03 · the fixture's entry date must stay INSIDE the report's
#: 90-day lookback window, so it is derived from today rather than written
#: down. `new_opportunity_outcomes.compute` skips any entry older than
#: `date.today() - 90 days`, and the hardcoded 2026-08-03 fixture aged past
#: that cutoff on 2026-11-02: the test passed for 90 days and then failed
#: permanently, with n_total=0 and nothing wrong with the code. A fixture
#: date that expires is a test that reports a defect it invented.
_FIXTURE_ENTRY_OFFSET_DAYS = 40      # comfortably inside the 90-day window
_FIXTURE_BAR_SPAN_DAYS = 60          # bars start before the entry


def _fixture_entry_date():
    from datetime import date, timedelta
    return (date.today() - timedelta(days=_FIXTURE_ENTRY_OFFSET_DAYS)).isoformat()


@pytest.fixture
def synthetic_root(tmp_path):
    """Build a fake parquet + Registry substrate."""
    from datetime import date, timedelta
    raw = tmp_path / "data" / "raw" / "india"
    raw.mkdir(parents=True)
    _start = (date.today() - timedelta(days=_FIXTURE_BAR_SPAN_DAYS)).isoformat()
    dates = pd.bdate_range(_start, periods=45)
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
        """CEO 2026-11-03 · now proves the monkeypatch actually took effect.

        This asserted only `n_total == 0`, which is also what you get when
        the patch target is wrong and the real (empty-ish) registry is
        read, or when every entry is filtered out for an unrelated reason.
        A test that passes for the wrong reason is how the sibling test
        below sat broken for two days without this one noticing.
        """
        called = []

        def fake_load(_root):
            called.append(_root)
            return {}

        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import new_opportunity_outcomes as _oo
        rep = _oo.compute(synthetic_root, "india")
        assert called, "the patched loader was never called"
        assert rep.n_total == 0

    def test_winner_gets_positive_forward_returns(self, synthetic_root, monkeypatch):
        """CEO 2026-11-03 · entry date derived from today, not written down.

        This failed with n_total=0 and the report was correct: `compute`
        skips entries older than `date.today() - 90 days`, the fixture's
        created_date was the literal "2026-08-03", and on 2026-11-03 that
        is 92 days old. The test passed until 2026-11-01 and then failed
        permanently without a line of production code changing.

        The assertion is unchanged - an empty report is still a failure,
        because the data contract says a fresh in-window entry with bars
        must produce an outcome. Only the fixture's clock is fixed.
        """
        entry = _fixture_entry_date()

        class _Opp:
            def __init__(self):
                self.ticker = "TESTWIN"; self.runner = "R2"
                self.market = "india"; self.status = "ACTIVE"
                self.created_date = entry
                self.closed_date = None
                self.opportunity_id = "TW-1"
            def is_active(self): return True
        def fake_load(_root): return {"x": [_Opp()]}
        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all", fake_load)
        from backend.research import new_opportunity_outcomes as _oo
        rep = _oo.compute(synthetic_root, "india")
        assert rep.n_total >= 1, (
            "an in-window entry with price bars must produce an outcome · "
            "entry=%s cutoff=90d" % entry)
        o = rep.outcomes[0]
        assert o["entry_date"] == entry
        # 5D forward should be positive (winner path · +2%/day fixture)
        assert o.get("fwd_5d_pct") is not None, (
            "the fixture provides 45 business days of bars from the entry, "
            "so a 5-day forward return must resolve")
        assert o["fwd_5d_pct"] > 0

    def test_an_entry_older_than_the_lookback_is_skipped(self, synthetic_root,
                                                         monkeypatch):
        """The behaviour that broke the test above · asserted deliberately.

        91 days is outside the 90-day window, so it must be skipped. This
        is the contract, not a defect - it just has to be stated, so the
        next expired fixture is diagnosed in seconds instead of being read
        as a broken report writer.
        """
        from datetime import date, timedelta
        stale = (date.today() - timedelta(days=91)).isoformat()

        class _Opp:
            def __init__(self):
                self.ticker = "TESTWIN"; self.runner = "R2"
                self.market = "india"; self.status = "ACTIVE"
                self.created_date = stale
                self.closed_date = None
                self.opportunity_id = "TW-OLD"
            def is_active(self): return True

        monkeypatch.setattr(
            "backend.research.opportunity_registry.load_all",
            lambda _r: {"x": [_Opp()]})
        from backend.research import new_opportunity_outcomes as _oo
        assert _oo.compute(synthetic_root, "india").n_total == 0
        # and a wider lookback picks it back up
        assert _oo.compute(synthetic_root, "india",
                           lookback_days=200).n_total == 1


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
