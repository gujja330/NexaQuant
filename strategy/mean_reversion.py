# strategy/mean_reversion.py
"""
MEAN-REVERSION sleeve — the portfolio diversifier that trades the RANGE regimes the
trend-follower sits out (Phase 4).

The trend playbook only fires in TREND regimes; in RANGE regimes it is idle (often most of
the time). A range-bound market mean-reverts: price stretched to the DISCOUNT edge tends to
bounce, price at the PREMIUM edge tends to fade. This sleeve harvests exactly those swings,
ACTIVE ONLY when the regime gate says 'range' — so it never fights a real trend (which is how
mean-reversion blows up). Exits on a fixed reward:risk target (not a momentum ride).

  long  : range regime AND deep discount (price in lower 25% of swing range) AND RSI oversold
  short : range regime AND deep premium  (price in upper 25% of swing range) AND RSI overbought

Symmetric long+short, ATR stop, config-driven thresholds. Validated in research/mean_reversion_test.py.
"""
import numpy as np
import pandas as pd
from strategy.smc import premium_discount
from strategy.meta_label import rsi


def entries(df, side="long", regime=None, rsi_n=14, rsi_os=35.0, rsi_ob=65.0):
    """Range-regime mean-reversion entries (fires when the condition turns ON)."""
    from strategy.playbook import regime_labels
    reg = regime if regime is not None else regime_labels(df, "adx")
    pd_ = premium_discount(df)
    r = rsi(df["close"], rsi_n)
    in_range = (reg.reindex(df.index) == "range")
    if side == "short":
        cond = in_range & (pd_["deep"] == -1) & (r >= rsi_ob)     # premium + overbought -> fade
    else:
        cond = in_range & (pd_["deep"] == 1) & (r <= rsi_os)      # discount + oversold -> bounce
    cond = cond.fillna(False).astype(bool)
    return cond & (~cond.shift(1, fill_value=False))


# mean-reversion exit: fixed target, tighter stop, short holding — NOT a trend ride
EXIT = dict(stop_mult=1.5, rr=1.0, max_bars=40)
