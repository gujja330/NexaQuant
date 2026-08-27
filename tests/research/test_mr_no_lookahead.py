"""M-R · no-lookahead property test.

Verifies feature enricher NEVER uses data from the future when computing
prediction-time features. This is the single most important property of the
research engine · without it every downstream study is contaminated.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from backend.research.mr_feature_enricher import (
    _rsi14, _ma_dist, _vol_pct, _momentum, _slice_upto,
)


def _mk_series(start_price=100.0, days=250, seed=42):
    import random
    r = random.Random(seed)
    closes = [start_price]
    for _ in range(days):
        closes.append(closes[-1] * (1 + r.uniform(-0.02, 0.02)))
    idx = pd.date_range("2025-01-01", periods=days+1, freq="B").strftime("%Y-%m-%d")
    return pd.DataFrame({"close": closes}, index=idx)


def test_slice_upto_returns_only_prior_data():
    df = _mk_series()
    iso = df.index[100]
    closes = _slice_upto(df, "close", iso, 50)
    assert len(closes) == 50
    for i, val in enumerate(closes):
        actual = df.loc[df.index[51 + i], "close"]
        assert abs(val - actual) < 1e-9, f"pos {i}: got {val}, expected {actual}"


def test_slice_upto_excludes_future_dates():
    df = _mk_series()
    iso = df.index[100]
    closes = _slice_upto(df, "close", iso, 50)
    for val in closes:
        found_dates = df.index[df["close"] == val].tolist()
        for d in found_dates:
            assert d <= iso, f"leaked future date {d} > {iso}"


def test_rsi_ma_vol_momentum_use_only_slice():
    df = _mk_series()
    iso = df.index[150]
    closes_at_iso = _slice_upto(df, "close", iso, 150)
    rsi_at_iso = _rsi14(closes_at_iso)
    ma20 = _ma_dist(closes_at_iso, 20)
    vol = _vol_pct(closes_at_iso, 20)
    mom = _momentum(closes_at_iso, 20)

    # Now tamper the future and recompute — result must be identical
    df2 = df.copy()
    df2.loc[df2.index[200:], "close"] *= 5.0
    closes_at_iso_v2 = _slice_upto(df2, "close", iso, 150)
    assert closes_at_iso == closes_at_iso_v2, "future edit changed past slice — leakage"
    assert _rsi14(closes_at_iso_v2) == rsi_at_iso
    assert _ma_dist(closes_at_iso_v2, 20) == ma20
    assert _vol_pct(closes_at_iso_v2, 20) == vol
    assert _momentum(closes_at_iso_v2, 20) == mom


def test_slice_returns_none_when_history_too_short():
    df = _mk_series(days=10)
    assert _slice_upto(df, "close", df.index[5], 50) is None


def test_rsi_bounds():
    df = _mk_series()
    closes = _slice_upto(df, "close", df.index[200], 100)
    r = _rsi14(closes)
    assert r is None or (0 <= r <= 100)


def test_ma_dist_scale():
    df = _mk_series(start_price=100.0, seed=1)
    closes = _slice_upto(df, "close", df.index[100], 100)
    d = _ma_dist(closes, 20)
    assert d is None or (-100 < d < 100)
