"""Canonical SMA · Constitution Article 30."""
from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.astype(float).rolling(window).mean()


def sma_last(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    v = sma(series, window).iloc[-1]
    return round(float(v), 4)
