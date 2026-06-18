# strategy/breakout.py
"""
VOLATILITY BREAKOUT (Donchian channel) — a different MECHANISM from the EMA momentum-ride
trend edge, on the same instruments. Enters on a clean break of an N-bar high/low (the start
of an expansion move) rather than on an established EMA trend, so its entries/exits differ in
timing and it can diversify the trend sleeve even on BTC/gold.

  long  : close breaks ABOVE the highest high of the prior `n` bars
  short : close breaks BELOW the lowest low of the prior `n` bars
Exit via the shared ATR-stop + momentum-ride machinery (trade_sim). Config-driven length.
"""
import pandas as pd


def entries(df, side="long", n=20):
    """Donchian breakout entries (fire when a new break occurs)."""
    hh = df["high"].rolling(n).max().shift(1)          # prior n-bar high (causal)
    ll = df["low"].rolling(n).min().shift(1)
    if side == "short":
        brk = df["close"] < ll
    else:
        brk = df["close"] > hh
    brk = brk.fillna(False).astype(bool)
    return brk & (~brk.shift(1, fill_value=False))     # only the bar the break first occurs
