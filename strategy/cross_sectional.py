# strategy/cross_sectional.py
"""
CROSS-SECTIONAL MOMENTUM — a second, UNCORRELATED edge for the portfolio.

Different in kind from our time-series trend edge: instead of "is THIS asset trending?",
it asks "which assets are strongest RELATIVE to the others?" and goes long the leaders /
short the laggards. This relative-strength edge tends to pay even when the whole basket is
choppy, so it diversifies the trend sleeve (the whole point of a consistent engine).

  - rank a universe by trailing momentum (lookback days, optional skip of the last few days)
  - long the top half, short the bottom half (dollar-neutral), equal weight, periodic rebalance
  - returns are net of turnover cost

Pure returns engine (continuous weights), so it composes cleanly in the portfolio allocator.
"""
import numpy as np
import pandas as pd


def momentum_rank_weights(closes, lookback=60, skip=5, long_only=False):
    """closes: DataFrame [date x symbol]. Returns target weights [date x symbol] in [-1,1],
    dollar-neutral (or long-only), equal-weighted within the long/short legs."""
    mom = closes.shift(skip) / closes.shift(lookback) - 1.0          # trailing return, skip recent
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    n = closes.shape[1]
    k = max(1, n // 2)                                               # size of each leg
    for dt, row in mom.iterrows():
        r = row.dropna()
        if len(r) < 2:
            continue
        order = r.sort_values(ascending=False)
        longs = order.index[:k]
        w.loc[dt, longs] = 1.0 / len(longs)
        if not long_only:
            shorts = order.index[-k:]
            w.loc[dt, shorts] = -1.0 / len(shorts)
    return w


def backtest_xsec(closes, lookback=60, skip=5, rebal=5, cost_bps=10.0, long_only=False):
    """Daily-compounded returns of the cross-sectional book. rebal = hold weights this many
    bars between rebalances; cost_bps charged on turnover at each rebalance."""
    rets = closes.pct_change().fillna(0.0)
    w_target = momentum_rank_weights(closes, lookback, skip, long_only)
    # hold weights between rebalances
    w_held = w_target.copy()
    mask = np.zeros(len(closes), dtype=bool); mask[::rebal] = True
    w_held[~mask] = np.nan
    w_held = w_held.ffill().fillna(0.0)
    gross = (w_held.shift(1) * rets).sum(axis=1)                     # next-bar pnl from held weights
    turnover = (w_held - w_held.shift(1)).abs().sum(axis=1)
    cost = turnover * (cost_bps / 1e4)
    return (gross - cost).rename("xsec")
