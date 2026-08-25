# tests/research/test_short_term_momentum.py
"""AEGIS · Sprint M · short-term momentum classifier + backtest tests."""
from __future__ import annotations

import pandas as pd
from pathlib import Path
import pytest


@pytest.fixture
def synthetic_root(tmp_path):
    raw = tmp_path / "data" / "raw" / "india"
    raw.mkdir(parents=True)
    dates = pd.date_range("2026-06-01", periods=90, freq="B")
    # RISER · +3% per day for last 5 days · nothing before
    closes = [100.0] * 80 + [100 * 1.03**i for i in range(1, 11)]
    df = pd.DataFrame({
        "open": closes, "high": closes, "low": closes,
        "close": closes,
        "tick_volume": [1000] * 80 + [5000] * 10,  # volume spike
        "spread": [0.0] * 90,
    }, index=dates)
    df.index.name = "time"
    df.to_parquet(raw / "RISER_D1.parquet")
    # FALLER
    closes_f = [100.0] * 80 + [100 * 0.97**i for i in range(1, 11)]
    df_f = df.copy(); df_f["close"] = closes_f
    df_f.to_parquet(raw / "FALLER_D1.parquet")
    return tmp_path


class TestCategorizer:

    def test_quick_rise_detected(self):
        from backend.research.short_term_momentum import categorize
        assert categorize(r1=5, r3=None, r5=None, r20=None) == "QUICK_RISE"

    def test_quick_fall_detected(self):
        from backend.research.short_term_momentum import categorize
        assert categorize(r1=-6, r3=None, r5=None, r20=None) == "QUICK_FALL"

    def test_sustained_up_needs_both_windows(self):
        from backend.research.short_term_momentum import categorize
        assert categorize(r1=None, r3=None, r5=6, r20=18) == "SUSTAINED_UP"

    def test_reversal_up_detected(self):
        from backend.research.short_term_momentum import categorize
        # 20d was down · 5d up = reversal
        assert categorize(r1=None, r3=None, r5=6, r20=-12) == "REVERSAL_UP"

    def test_flat_is_ignore(self):
        from backend.research.short_term_momentum import categorize
        assert categorize(r1=0.5, r3=1, r5=2, r20=3) == "IGNORE"

    def test_vol_adjustment_higher_threshold(self):
        from backend.research.short_term_momentum import categorize
        # +5% would normally be QUICK_RISE · but at 2x vol adjust
        # threshold is 8% · so this becomes IGNORE
        assert categorize(r1=5, r3=None, r5=None, r20=None,
                          vol_adjust=2.0) == "IGNORE"


class TestVerdict:

    def test_quality_high_quick_rise_potential_entry(self):
        from backend.research.short_term_momentum import verdict_for
        v, _ = verdict_for("QUICK_RISE", "QUALITY")
        assert v == "POTENTIAL_ENTRY"

    def test_quality_low_quick_rise_is_pump_risk(self):
        from backend.research.short_term_momentum import verdict_for
        v, _ = verdict_for("QUICK_RISE", "AVOID")
        assert v == "PUMP_RISK"

    def test_quality_high_quick_fall_is_rebound_watch(self):
        from backend.research.short_term_momentum import verdict_for
        v, _ = verdict_for("QUICK_FALL", "QUALITY")
        assert v == "REBOUND_WATCH"

    def test_quality_low_quick_fall_is_avoid(self):
        from backend.research.short_term_momentum import verdict_for
        v, _ = verdict_for("QUICK_FALL", "AVOID")
        assert v == "AVOID"


class TestComputeLive:

    def test_riser_is_detected(self, synthetic_root):
        from backend.research import short_term_momentum as _sm
        rep = _sm.compute(synthetic_root, "india")
        tks = [c["ticker"] for c in rep.candidates]
        assert "RISER" in tks or rep.n_quick_rise > 0 or rep.n_sustained_up > 0

    def test_summary_line(self, synthetic_root):
        from backend.research import short_term_momentum as _sm
        rep = _sm.compute(synthetic_root, "india")
        s = _sm.summary_line(rep)
        assert "short_term_momentum" in s


class TestBacktest:

    def test_backtest_returns_report(self, synthetic_root):
        from backend.research import short_term_momentum_backtest as _bt
        rep = _bt.compute(synthetic_root, "india", lookback_days=30,
                          universe_limit=5)
        assert rep.market == "india"

    def test_backtest_summary_line(self, synthetic_root):
        from backend.research import short_term_momentum_backtest as _bt
        rep = _bt.compute(synthetic_root, "india", lookback_days=30,
                          universe_limit=5)
        s = _bt.summary_line(rep)
        assert "momentum_backtest" in s
