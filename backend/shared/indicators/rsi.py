"""Canonical RSI · Wilder + simple-rolling variants · Constitution Article 30.

The ONLY RSI implementation in AEGIS. All engines import from here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(closes: pd.Series, period: int = 14, method: str = "simple") -> float | None:
    """Return the last-bar RSI value in [0, 100].

    method: "simple" (rolling mean of gains/losses · matches feature_store
    convention) or "wilder" (EWM with alpha = 1/n · matches broker convention).
    Returns None if history is insufficient.
    """
    if len(closes) <= period:
        return None
    d = closes.astype(float).diff().dropna()
    up = d.clip(lower=0)
    dn = (-d.clip(upper=0))
    if method == "wilder":
        up_avg = up.ewm(alpha=1.0 / period, adjust=False).mean()
        dn_avg = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    else:
        up_avg = up.rolling(period).mean()
        dn_avg = dn.rolling(period).mean()
    rs = up_avg / dn_avg.replace(0, np.nan)
    r = 100 - (100 / (1 + rs))
    v = r.iloc[-1]
    return round(float(v), 3) if pd.notna(v) else None


def rsi_series(closes: pd.Series, period: int = 14, method: str = "simple") -> pd.Series:
    """Return full RSI series."""
    d = closes.astype(float).diff()
    up = d.clip(lower=0)
    dn = (-d.clip(upper=0))
    if method == "wilder":
        up_avg = up.ewm(alpha=1.0 / period, adjust=False).mean()
        dn_avg = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    else:
        up_avg = up.rolling(period).mean()
        dn_avg = dn.rolling(period).mean()
    rs = up_avg / dn_avg.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
