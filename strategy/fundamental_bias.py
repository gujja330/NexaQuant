# strategy/fundamental_bias.py
"""
FUNDAMENTAL bias gate — turn the macro feature layer (data/fundamentals.py) into a
directional bias the strategy can act on, not just an ML feature.

Gold: bullish when US real yields AND the dollar (DXY) are FALLING (the two strongest,
best-documented gold drivers). f_real_yield_trend / f_dxy_trend are already built leakage-
safe (+ve = the driver is falling = gold-bullish), so the macro bias is simply their mean.

Usage: entries can require macro bias to AGREE with the trade side (long only when macro
bullish, short only when bearish) — the "fundamentals confirm technicals" filter. Gated
per-symbol via config (instruments.<SYM>.macro_gate); BTC stays off (these are gold drivers).

Leakage-safe: macro values are stamped to the day AFTER release and joined backward.
"""
import pandas as pd
from data.fundamentals import load_fundamentals

GOLD_COLS = ["f_real_yield_trend", "f_dxy_trend"]


def macro_bias(df):
    """Per-bar macro bias in roughly [-1, 1] aligned to df.index: >0 gold-bullish (yields/USD
    falling), <0 gold-bearish. Returns all-zeros (neutral) if no FUNDAMENTALS.parquet yet, so
    the gate is a safe no-op until the macro pull has run."""
    f = load_fundamentals(df.index)
    cols = [c for c in GOLD_COLS if c in f.columns]
    if not cols:
        return pd.Series(0.0, index=df.index)
    return f[cols].mean(axis=1).reindex(df.index).fillna(0.0)


def macro_agrees(df, side, thresh=0.0):
    """True where macro bias agrees with the side by at least `thresh`.
      long  -> bias >=  thresh    (macro bullish)
      short -> bias <= -thresh    (macro bearish)
    thresh=0 -> only require the correct sign."""
    b = macro_bias(df)
    return (b >= thresh) if side == "long" else (b <= -thresh)
