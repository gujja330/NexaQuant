"""Canonical returns · Constitution Article 30 · point-to-point + compound."""
from __future__ import annotations

import pandas as pd


def returns_pct(series: pd.Series, window: int) -> float | None:
    """Point-to-point return over `window` bars, expressed as percent."""
    if len(series) <= window:
        return None
    a = float(series.iloc[-window - 1])
    b = float(series.iloc[-1])
    if a <= 0:
        return None
    return round((b / a - 1.0) * 100, 4)


def returns_series(series: pd.Series) -> pd.Series:
    """Full daily-return series."""
    return series.astype(float).pct_change()
