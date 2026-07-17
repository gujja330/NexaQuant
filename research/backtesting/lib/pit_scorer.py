"""Point-in-time company scorer for DEV021 backtesting.

Given a ticker's OHLCV series and a backtest date T, compute a lightweight
version of the DEV020 composite using only bars up to T. NO LOOK-AHEAD.

Uses the same 11-dimension formulas as DEV020 but restricted to the subset
that can be computed from raw OHLCV alone. Sector/industry-relative dimensions
are deferred to v0.2 (would require rebuilding DEV018/019 aggregates at each PIT
date; documented in README).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


# Same weights as DEV020 for the dimensions we CAN compute PIT
# Note: rs_industry, rs_sector are dropped in v0.1; their weights redistribute
# proportionally to the remaining dimensions.
PIT_WEIGHTS = {
    "momentum":       0.20,
    "rs_nifty":       0.15,
    "trend":          0.13,
    "volatility":     0.10,
    "drawdown":       0.10,
    "position_52w":   0.10,
    "liquidity":      0.08,
    "volume_trend":   0.07,
    "breakout":       0.05,
    "technical":      0.02,
}
assert abs(sum(PIT_WEIGHTS.values()) - 1.0) < 1e-6


@dataclass
class PitScore:
    ticker: str
    asof: pd.Timestamp
    score: float                                    # 0-100
    dimension_values: dict                          # per-dimension 0-100
    confidence: float
    latest_close: float
    n_bars: int


def _percentile(series: pd.Series, current: float) -> float:
    s = series.dropna()
    if len(s) < 20:
        return 50.0
    return float((s <= current).sum()) / len(s) * 100


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_ticker_at(df: pd.DataFrame, asof: pd.Timestamp,
                     nifty_series: pd.Series | None = None,
                     min_bars: int = 100) -> PitScore | None:
    """Score a single ticker using only bars up to `asof`.

    df must be indexed by date and contain 'close' (+ optionally 'tick_volume').
    Returns None if insufficient history at asof.
    """
    if df.empty or "close" not in df.columns:
        return None

    # POINT-IN-TIME slice — this is the anti-look-ahead guarantee
    slice_df = df.loc[df.index <= asof]
    close = slice_df["close"].dropna()
    if len(close) < min_bars:
        return None

    latest = float(close.iloc[-1])

    dims: dict[str, float] = {}

    # ── Momentum (blend of 20/60/120d percentiles) ──────────────────────────
    mom_percentiles = []
    for n in (20, 60, 120):
        if len(close) < n + 30:
            continue
        cur = (close.iloc[-1] / close.iloc[-n - 1] - 1) * 100
        hist = close.pct_change(n).dropna() * 100
        if len(hist) >= 30:
            mom_percentiles.append(_percentile(hist, cur))
    if mom_percentiles:
        dims["momentum"] = sum(mom_percentiles) / len(mom_percentiles)

    # ── Trend: price above N of {20/50/100/200} DMAs ────────────────────────
    mas = []
    for n in (20, 50, 100, 200):
        if len(close) >= n:
            mas.append(float(close.tail(n).mean()))
    if mas:
        above = sum(1 for m in mas if latest > m)
        dims["trend"] = (above / len(mas)) * 100

    # ── RS vs Nifty ─────────────────────────────────────────────────────────
    if nifty_series is not None and len(nifty_series) >= 40:
        # Slice nifty to <= asof too
        nifty_slice = nifty_series.loc[nifty_series.index <= asof]
        if len(nifty_slice) >= 40:
            aligned = pd.concat([close.rename("c"), nifty_slice.rename("n")],
                                  axis=1).dropna()
            if len(aligned) >= 40:
                rs_cur = (aligned["c"].iloc[-1] / aligned["c"].iloc[-21] - 1) \
                          - (aligned["n"].iloc[-1] / aligned["n"].iloc[-21] - 1)
                rs_hist = (aligned["c"].pct_change(20) - aligned["n"].pct_change(20)).dropna()
                dims["rs_nifty"] = _percentile(rs_hist, rs_cur)

    # ── Volatility (inverted: lower = better) ───────────────────────────────
    if len(close) >= 30:
        r = close.pct_change().dropna()
        vol_cur = float(r.tail(20).std() * math.sqrt(252) * 100) if len(r) >= 21 else None
        if vol_cur is not None:
            vol_hist = r.rolling(20).std().dropna() * math.sqrt(252) * 100
            if len(vol_hist) >= 30:
                dims["volatility"] = 100.0 - _percentile(vol_hist, vol_cur)

    # ── Drawdown (inverted) ─────────────────────────────────────────────────
    if len(close) >= 30:
        window = close.tail(min(252, len(close)))
        peak = window.cummax()
        dd = float(((window / peak) - 1).min() * 100)
        dims["drawdown"] = _clamp(100.0 + dd * 2.5)

    # ── 52-week position ────────────────────────────────────────────────────
    if len(close) >= 30:
        window = close.tail(min(252, len(close)))
        lo, hi = float(window.min()), float(window.max())
        if hi > lo:
            dims["position_52w"] = _clamp((latest - lo) / (hi - lo) * 100)
        else:
            dims["position_52w"] = 50.0

    # ── Breakout (proxy = 52w position; same value, semantic tag) ───────────
    if "position_52w" in dims:
        dims["breakout"] = dims["position_52w"]

    # ── Liquidity + volume trend ────────────────────────────────────────────
    vol_col = slice_df["tick_volume"].dropna() if "tick_volume" in slice_df.columns else pd.Series(dtype=float)
    if len(vol_col) >= 90:
        v20 = float(vol_col.tail(20).mean())
        v90 = float(vol_col.tail(90).mean())
        if v90 > 0:
            dims["volume_trend"] = _clamp((v20 / v90 - 0.5) * 100)

        # Liquidity = ADV in INR crore percentile
        adv_series = (close * vol_col.reindex(close.index)).dropna().rolling(20).mean() / 1e7
        adv_series = adv_series.dropna()
        if len(adv_series) >= 30:
            dims["liquidity"] = _percentile(adv_series, float(adv_series.iloc[-1]))

    # ── Technical strength (blend) ──────────────────────────────────────────
    parts = [dims[k] for k in ("momentum", "trend", "rs_nifty") if k in dims]
    if parts:
        dims["technical"] = sum(parts) / len(parts)

    # ── Composite (renormalise by present weights) ──────────────────────────
    weighted_sum = 0.0
    weight_sum = 0.0
    for k, w in PIT_WEIGHTS.items():
        if k in dims:
            weighted_sum += w * dims[k]
            weight_sum += w

    if weight_sum == 0:
        return None

    score = weighted_sum / weight_sum
    completeness = weight_sum
    confidence = min(1.0, completeness)

    return PitScore(
        ticker=df.attrs.get("ticker", "UNKNOWN"),
        asof=asof, score=_clamp(score),
        dimension_values=dims, confidence=confidence,
        latest_close=latest, n_bars=len(close),
    )
