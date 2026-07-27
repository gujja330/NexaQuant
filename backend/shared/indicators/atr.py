"""Canonical ATR · true-range from real H/L/C · Constitution Article 30.

The ONLY ATR implementation in AEGIS.
"""
from __future__ import annotations

import pandas as pd


def atr_pct(df: pd.DataFrame, period: int = 14) -> float | None:
    """ATR as % of last close · true-range based (H-L, |H-prev_close|, |L-prev_close|).

    Requires columns: high · low · close.
    Returns None if history insufficient or H/L absent.
    """
    if len(df) <= period + 1:
        return None
    if "high" not in df.columns or "low" not in df.columns:
        return None
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    tr = pd.concat([high - low,
                     (high - prev_close).abs(),
                     (low  - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    close = float(df["close"].iloc[-1])
    if pd.isna(atr) or close <= 0:
        return None
    return round(float(atr / close * 100), 4)


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Return full ATR series (absolute · not pct)."""
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    tr = pd.concat([high - low,
                     (high - prev_close).abs(),
                     (low  - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()
