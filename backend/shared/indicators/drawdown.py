"""Canonical drawdown · Constitution Article 30."""
from __future__ import annotations

import pandas as pd


def max_drawdown_pct(closes: pd.Series, window: int = 60) -> float | None:
    """Trailing max drawdown over `window` bars, as negative %."""
    if len(closes) < window:
        return None
    tail = closes.astype(float).tail(window)
    running_max = tail.cummax()
    dd = (tail / running_max - 1) * 100
    v = dd.min()
    return round(float(v), 3) if pd.notna(v) else None
