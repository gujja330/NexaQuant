"""Canonical EMA · Constitution Article 30."""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average · adjust=False for Wilder-style consistency."""
    return series.astype(float).ewm(span=span, adjust=False).mean()


def ema_last(series: pd.Series, span: int) -> float | None:
    if len(series) < span:
        return None
    v = ema(series, span).iloc[-1]
    return round(float(v), 4)
