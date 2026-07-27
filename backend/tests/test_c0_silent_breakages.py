"""Wave 3 · Phase C0 · regression suite for silent-breakage fixes.

Covers:
- M-F1  ATR now consumes real H/L/C (dead-code proxy branch removed)
- M-F2  ADX rewritten to textbook Wilder using real H/L
- M-Sec1  sector_context.json list-shape extraction (both adapters + macro_intel)

Each test asserts the specific behaviour the audit flagged as broken so a
future refactor cannot silently regress.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
try:
    import pytest  # noqa: F401
    _APPROX = pytest.approx
except ModuleNotFoundError:  # graceful fallback for environments without pytest
    class _ApproxShim:
        def __call__(self, target, abs=1e-6, rel=None):
            class _Cmp:
                def __init__(self, t, a): self.t, self.a = t, a
                def __eq__(self, other): return abs_(other - self.t) <= self.a
            from builtins import abs as abs_
            return _Cmp(target, abs)
    _APPROX = _ApproxShim()

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.feature_store.features import technical as tech  # noqa: E402
from backend.macro_intel.sector_rotation import compute_sector_rotation  # noqa: E402


# ── M-F1  ATR consumes real HLC ────────────────────────────────────────
def _synthetic_bars(n: int = 60, close_start: float = 100.0,
                     hl_spread_pct: float = 0.03, seed: int = 0):
    """Deterministic price walk with a fixed H/L spread. seed=0 uses index
    for reproducibility instead of Math.random-like variance."""
    rows = []
    close = close_start
    for i in range(n):
        # deterministic pseudo-move: +0.4% up on even bars, -0.3% down on odd
        move = 0.004 if i % 2 == 0 else -0.003
        close = close * (1.0 + move)
        h = close * (1.0 + hl_spread_pct / 2)
        l = close * (1.0 - hl_spread_pct / 2)
        rows.append({"close": close, "high": h, "low": l})
    return pd.DataFrame(rows)


def test_M_F1_atr_uses_real_high_low():
    """ATR must return the true-range %, not a mechanical ±0.5% proxy."""
    df = _synthetic_bars(n=60, hl_spread_pct=0.03)  # 3% H/L spread
    atr = tech._atr(df, period=14)
    assert atr is not None
    # With a 3% H/L spread, ATR should be at least ~2.5% (true range dominated
    # by H-L). The old proxy branch would have returned ~1% (0.5%×2).
    assert atr >= 2.0, f"ATR should reflect real 3% H/L spread; got {atr}"


def test_M_F1_atr_returns_none_without_hl_columns():
    """Regression: no more silent proxy fallback. Missing H/L → None."""
    df = pd.DataFrame({"close": [100.0 + i for i in range(30)]})
    assert tech._atr(df, period=14) is None


def test_M_F1_atr_scales_with_hl_spread():
    """Widening the H/L spread must produce a larger ATR value."""
    tight = tech._atr(_synthetic_bars(hl_spread_pct=0.01), 14)
    wide  = tech._atr(_synthetic_bars(hl_spread_pct=0.05), 14)
    assert tight is not None and wide is not None
    assert wide > tight * 1.5, f"ATR should scale with H/L spread; tight={tight} wide={wide}"


# ── M-F2  ADX uses real H/L ────────────────────────────────────────────
def test_M_F2_adx_uses_real_high_low():
    """ADX must return a bounded [0, 100] value from real H/L, not a
    close-only proxy. Missing H/L → None (no silent fallback)."""
    df = _synthetic_bars(n=80, hl_spread_pct=0.03)
    adx = tech._adx(df, period=14)
    assert adx is not None
    assert 0.0 <= adx <= 100.0, f"ADX out of range: {adx}"


def test_M_F2_adx_returns_none_without_hl_columns():
    df = pd.DataFrame({"close": [100.0 + i * 0.5 for i in range(60)]})
    assert tech._adx(df, period=14) is None


def test_M_F2_adx_higher_on_trending_series():
    """Strong monotonic uptrend → higher ADX than choppy sideways."""
    # Monotonic uptrend
    n = 80
    trend_close = [100.0 * (1.02 ** i) for i in range(n)]
    trend_df = pd.DataFrame({
        "close": trend_close,
        "high":  [c * 1.005 for c in trend_close],
        "low":   [c * 0.995 for c in trend_close],
    })
    # Choppy sideways
    chop_close = [100.0 + (2 if i % 2 == 0 else -2) for i in range(n)]
    chop_df = pd.DataFrame({
        "close": chop_close,
        "high":  [c * 1.01 for c in chop_close],
        "low":   [c * 0.99 for c in chop_close],
    })
    trend_adx = tech._adx(trend_df, 14)
    chop_adx  = tech._adx(chop_df, 14)
    assert trend_adx is not None and chop_adx is not None
    assert trend_adx > chop_adx, f"trend ADX {trend_adx} should exceed chop ADX {chop_adx}"


# ── DataFrame construction now includes H/L ────────────────────────────
@dataclass
class _StubBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class _StubDataset:
    rows: list = field(default_factory=list)


def test_technical_compute_now_produces_nonzero_atr_and_adx():
    """End-to-end: bars with H/L present must yield non-null atr_14_pct and
    adx_14 in the compute() output. Prior to Phase C0 both were near-constant
    proxies or null."""
    today = date(2026, 7, 27)
    rows = []
    close = 100.0
    for i in range(80):
        d = today - timedelta(days=80 - i)
        close = close * (1.004 if i % 2 == 0 else 0.997)
        rows.append(_StubBar(
            symbol="TEST", date=d,
            open=close * 0.999, high=close * 1.015,
            low=close * 0.985, close=close, volume=1_000_000,
        ))
    canon = {"bar": _StubDataset(rows=rows)}
    out = tech.compute(canon, universe=["TEST"], asof=today, market_name="india")
    assert "TEST" in out
    r = out["TEST"]
    assert r.get("atr_14_pct") is not None, "ATR should populate with real H/L"
    assert r["atr_14_pct"] > 1.0, f"ATR should reflect 3% H/L spread; got {r['atr_14_pct']}"
    assert r.get("adx_14") is not None, "ADX should populate with real H/L"


# ── M-Sec1  sector_context.json list-shape extraction ──────────────────
def test_M_Sec1_sector_rotation_accepts_list_shape():
    """DEV018 emits `sectors` as a LIST of {display_name, score(0-100), ...}.
    Prior code checked isinstance(sectors, dict) only → silently zero rows."""
    context = {
        "sectors": [
            {"sector_key": "sector.india.pharma", "display_name": "Pharma",
             "score": 80.5, "classification": "Strong-Bullish"},
            {"sector_key": "sector.india.realty", "display_name": "Realty",
             "score": 76.7, "classification": "Strong-Bullish"},
            {"sector_key": "sector.india.metal",  "display_name": "Metal",
             "score": 42.0, "classification": "Bearish"},
            {"sector_key": "sector.india.it",     "display_name": "IT",
             "score": 30.0, "classification": "Bearish"},
        ],
    }
    reading = compute_sector_rotation("india", date(2026, 7, 27),
                                        sector_context=context)
    # Prior bug: sector_returns would be empty dict.
    assert len(reading.sector_returns) == 4, \
        f"list-shape extraction failed: got {reading.sector_returns}"
    # Ranking preserved: Pharma > Realty > Metal > IT
    ranked = list(reading.sector_returns.keys())
    assert ranked[0] == "Pharma"
    assert ranked[-1] == "IT"
    # Leaders/laggards non-empty
    assert len(reading.leaders) == 3
    assert len(reading.laggards) == 3
    assert reading.leaders[0]["sector"] == "Pharma"
    assert reading.laggards[0]["sector"] == "IT"
    # rotation_strength must be > 0 (previously 0.0)
    assert reading.rotation_strength > 0.0


def test_M_Sec1_sector_rotation_dict_shape_still_works():
    """Backward-compat: legacy dict shape must still extract correctly."""
    context = {
        "sectors": {
            "Pharma": {"return_pct": 3.5, "mean_return_pct": 3.5},
            "IT":     {"return_pct": -1.2},
        },
    }
    reading = compute_sector_rotation("india", date(2026, 7, 27),
                                        sector_context=context)
    assert len(reading.sector_returns) == 2
    assert reading.sector_returns["Pharma"] == 3.5
    assert reading.sector_returns["IT"] == -1.2


def test_M_Sec1_sector_rotation_empty_when_absent():
    """No sector_context → empty reading, no crash."""
    reading = compute_sector_rotation("india", date(2026, 7, 27),
                                        sector_context=None)
    assert reading.sector_returns == {}


def test_M_Sec1_score_mapping_is_symmetric_around_50():
    """A sector with score=50 should map to return_pct=0.0."""
    context = {"sectors": [
        {"sector_key": "sector.india.neutral", "display_name": "Neutral",
         "score": 50.0},
    ]}
    reading = compute_sector_rotation("india", date(2026, 7, 27),
                                        sector_context=context)
    assert reading.sector_returns.get("Neutral") == _APPROX(0.0)
