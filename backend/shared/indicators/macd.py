"""Canonical MACD · Constitution Article 30."""
from __future__ import annotations

import pandas as pd


def macd(closes: pd.Series,
          fast: int = 12, slow: int = 26, signal: int = 9
          ) -> tuple[float | None, float | None, float | None]:
    """Return (macd, signal, histogram) at last bar. None if history insufficient."""
    if len(closes) < slow + signal:
        return None, None, None
    c = closes.astype(float)
    ema_fast = c.ewm(span=fast, adjust=False).mean()
    ema_slow = c.ewm(span=slow, adjust=False).mean()
    m = ema_fast - ema_slow
    s = m.ewm(span=signal, adjust=False).mean()
    h = m - s
    return (round(float(m.iloc[-1]), 4),
            round(float(s.iloc[-1]), 4),
            round(float(h.iloc[-1]), 4))
