"""AEGIS USA · Technical Indicators.

Deterministic 6-dimension scoring per ticker from daily OHLCV
parquet. Same dimension set as India's learning.parquet:

  dim_momentum       — 20-day price momentum, percentile-normalised
  dim_trend          — 20d SMA vs 50d SMA (positive → uptrend)
  dim_rs_spx         — relative strength vs S&P 500 (^GSPC)
  dim_volatility     — annualised 20-day realised vol, INVERTED
                       (lower vol = higher score)
  dim_drawdown       — inverted current drawdown from 52w high
  dim_position_52w   — where price sits in the 52-week range

All dimensions output on 0..100 scale. Sorted iteration.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


_USA = Path(__file__).resolve().parents[3]
RAW_DIR = _USA / "data" / "raw" / "us"
SPX_PATH = RAW_DIR / "_IDX_GSPC_D1.parquet"


def load_close(ticker: str) -> pd.Series | None:
    p = RAW_DIR / f"{ticker}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    if df.empty or "close" not in df.columns: return None
    df = df.sort_index()
    return df["close"].astype(float).dropna()


def load_spx() -> pd.Series | None:
    if not SPX_PATH.exists(): return None
    try:
        df = pd.read_parquet(SPX_PATH)
    except Exception:
        return None
    return df["close"].astype(float).dropna().sort_index() if "close" in df.columns else None


def _to_0_100(x: float, lo: float, hi: float) -> float:
    if hi <= lo: return 50.0
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))


def compute_dimensions(close: pd.Series, spx: pd.Series | None = None) -> dict:
    """Return the 6-dimension technical vector for one ticker.

    Requires ≥ 252 daily bars (roughly 1 year). If short, returns
    dimensions set to 50 (neutral) so the ticker isn't rejected outright.
    """
    if close is None or len(close) < 60:
        return {
            "dim_momentum": None, "dim_trend": None, "dim_rs_spx": None,
            "dim_volatility": None, "dim_drawdown": None, "dim_position_52w": None,
            "note": "insufficient history",
        }

    latest = close.iloc[-1]

    # 1. Momentum: 20-day return
    if len(close) >= 21:
        mom_20 = (close.iloc[-1] / close.iloc[-21]) - 1.0
    else:
        mom_20 = 0.0
    # Historical distribution to bucket into 0..100
    hist_mom = close.pct_change(20).dropna()
    if not hist_mom.empty:
        p_lo, p_hi = float(hist_mom.quantile(0.05)), float(hist_mom.quantile(0.95))
        dim_momentum = _to_0_100(mom_20, p_lo, p_hi)
    else:
        dim_momentum = 50.0

    # 2. Trend: SMA20 vs SMA50 (positive = uptrend). Scale by SMA50.
    sma20 = float(close.tail(20).mean())
    sma50 = float(close.tail(50).mean()) if len(close) >= 50 else sma20
    trend_ratio = (sma20 - sma50) / sma50 if sma50 else 0.0
    # Typical trend ratio ranges ±5%; map [-0.05, +0.05] → [0, 100]
    dim_trend = _to_0_100(trend_ratio, -0.05, 0.05)

    # 3. Relative strength vs S&P 500 over 20 days
    if spx is not None and not spx.empty and len(spx) >= 21 and len(close) >= 21:
        stock_ret = (close.iloc[-1] / close.iloc[-21]) - 1.0
        # Align spx to stock's window
        s = spx[spx.index <= close.index[-1]]
        if len(s) >= 21:
            spx_ret = (s.iloc[-1] / s.iloc[-21]) - 1.0
            rs = stock_ret - spx_ret
            # Historical RS distribution over 20d
            spx_ret_series = spx.pct_change(20)
            stk_ret_series = close.pct_change(20)
            # Align + compute rs history
            joined = pd.concat([stk_ret_series, spx_ret_series], axis=1, join="inner").dropna()
            if not joined.empty:
                joined.columns = ["stk", "spx"]
                rs_series = joined["stk"] - joined["spx"]
                p_lo, p_hi = float(rs_series.quantile(0.05)), float(rs_series.quantile(0.95))
                dim_rs_spx = _to_0_100(rs, p_lo, p_hi)
            else:
                dim_rs_spx = 50.0
        else:
            dim_rs_spx = 50.0
    else:
        dim_rs_spx = 50.0

    # 4. Volatility: annualised 20d realised vol — LOWER = higher score
    if len(close) >= 21:
        vol_20 = float(close.pct_change().tail(20).std() * (252 ** 0.5))
        # Vol regime: 10% (low, score 100) to 60% (high, score 0)
        dim_volatility = 100.0 - _to_0_100(vol_20, 0.10, 0.60)
    else:
        dim_volatility = 50.0

    # 5. Drawdown: current DD from 252-day peak — inverted (less DD = higher score)
    peak_252 = float(close.tail(252).max()) if len(close) >= 100 else float(close.max())
    dd = (latest - peak_252) / peak_252 if peak_252 > 0 else 0.0    # negative
    # Map: 0% DD → 100, -30% DD → 0
    dim_drawdown = 100.0 - _to_0_100(-dd, 0.0, 0.30)

    # 6. Position in 52-week range: (latest - 52w_low) / (52w_high - 52w_low)
    hi52 = float(close.tail(252).max())
    lo52 = float(close.tail(252).min())
    if hi52 > lo52:
        dim_position_52w = (latest - lo52) / (hi52 - lo52) * 100
    else:
        dim_position_52w = 50.0

    return {
        "dim_momentum":     round(float(dim_momentum), 2),
        "dim_trend":        round(float(dim_trend), 2),
        "dim_rs_spx":       round(float(dim_rs_spx), 2),
        "dim_volatility":   round(float(dim_volatility), 2),
        "dim_drawdown":     round(float(dim_drawdown), 2),
        "dim_position_52w": round(float(dim_position_52w), 2),
    }


def technical_score(dims: dict) -> float | None:
    """Weighted composite of the 6 dimensions → single 0..100 score."""
    weights = {
        "dim_momentum":     0.20,
        "dim_trend":        0.20,
        "dim_rs_spx":       0.20,
        "dim_volatility":   0.15,
        "dim_drawdown":     0.10,
        "dim_position_52w": 0.15,
    }
    total_w = 0.0
    total_v = 0.0
    for k, w in weights.items():
        v = dims.get(k)
        if v is None: continue
        total_w += w
        total_v += w * v
    if total_w == 0: return None
    return round(total_v / total_w, 2)
