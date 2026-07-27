"""Canonical volatility · Constitution Article 30 · daily + annualized variants."""
from __future__ import annotations

import math

import pandas as pd

TRADING_DAYS_YEAR = 252


def volatility_daily(closes: pd.Series, window: int = 20) -> float | None:
    """Rolling stdev of daily returns · NOT annualized."""
    if len(closes) < window + 1:
        return None
    r = closes.astype(float).pct_change().dropna().tail(window)
    if r.empty:
        return None
    return round(float(r.std()), 6)


def volatility_annualized(closes: pd.Series, window: int = 20) -> float | None:
    """Rolling stdev of daily returns × sqrt(TRADING_DAYS_YEAR)."""
    v = volatility_daily(closes, window)
    if v is None:
        return None
    return round(v * math.sqrt(TRADING_DAYS_YEAR), 6)
