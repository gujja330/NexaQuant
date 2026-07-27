"""Canonical ADX · textbook Wilder using real H/L · Constitution Article 30."""
from __future__ import annotations

import numpy as np
import pandas as pd


def adx(df: pd.DataFrame, period: int = 14) -> float | None:
    """Return last-bar ADX in [0, 100]. Requires columns: high · low · close.
    Returns None if history insufficient or H/L absent."""
    if len(df) <= period * 2:
        return None
    if "high" not in df.columns or "low" not in df.columns:
        return None
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)
    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm  = ((up_move   > down_move) & (up_move   > 0)).astype(float) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move)   & (down_move > 0)).astype(float) * down_move.clip(lower=0)
    prev_close = close.shift(1)
    tr = pd.concat([high - low,
                     (high - prev_close).abs(),
                     (low  - prev_close).abs()], axis=1).max(axis=1)
    atr_smoothed = tr.rolling(period).mean()
    plus_di  = 100.0 * plus_dm.rolling(period).mean()  / atr_smoothed.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.rolling(period).mean() / atr_smoothed.replace(0, np.nan)
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denom
    a = dx.rolling(period).mean().iloc[-1]
    return round(float(a), 3) if pd.notna(a) else None
