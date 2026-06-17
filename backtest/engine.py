# backtest/engine.py
"""
Shared, leakage-free, cost-aware backtest engine. Used by all research probes so
every strategy is measured the same honest way.

Contract:
  target_pos : desired position in {-1,0,+1} decided at CLOSE of bar t.
               The engine shifts it by 1 (enter at next bar OPEN) -> no look-ahead.
  cost_rt    : round-trip cost in $/oz, charged whenever the held position changes.
"""
import numpy as np
import pandas as pd

BARS_PER_YEAR = {"M5": 288 * 252, "M15": 96 * 252, "H1": 24 * 252,
                 "H4": 6 * 252, "D1": 252, "W1": 52}


def backtest(df, target_pos, cost_rt):
    px_open = df["open"]
    pos = target_pos.reindex(df.index).shift(1).fillna(0)
    gross = pos * (px_open.shift(-1) - px_open)
    cost = pos.diff().abs().fillna(pos.abs()) * cost_rt
    net = (gross - cost).dropna()
    trades, cur, ep = [], 0, None
    for t, p in pos.items():
        if p != cur:
            if cur != 0 and ep is not None:
                trades.append({"pnl": cur * (px_open.get(t, np.nan) - ep) - cost_rt})
            cur, ep = p, (px_open.get(t, np.nan) if p != 0 else None)
    return net, pd.DataFrame(trades)


def stats(net, tr, notional, tf):
    if len(net) == 0 or tr is None or tr.empty:
        return None
    eq = net.cumsum()
    dd = (eq.cummax() - eq).max()
    sh = (net.mean() / net.std()) * np.sqrt(BARS_PER_YEAR[tf]) if net.std() > 0 else 0.0
    wins = tr["pnl"] > 0
    gl = -tr.loc[~wins, "pnl"].sum()
    pf = (tr.loc[wins, "pnl"].sum() / gl) if gl > 0 else np.inf
    return dict(trades=len(tr), win=wins.mean(), exp=tr["pnl"].mean(), pf=pf,
                total=eq.iloc[-1], dd=dd, sharpe=sh, ret_pct=100 * eq.iloc[-1] / notional)


def print_row(name, seg, s):
    if s is None:
        print(f"{name:<34}{seg:<5}{'(no trades)':>8}")
    else:
        print(f"{name:<34}{seg:<5}{s['trades']:>7}{100*s['win']:>6.1f}{s['exp']:>8.2f}"
              f"{s['pf']:>6.2f}{s['total']:>9.1f}{s['dd']:>8.1f}{s['sharpe']:>8.2f}{s['ret_pct']:>7.1f}")


HEADER = (f"{'strategy':<34}{'seg':<5}{'trades':>7}{'win%':>7}{'exp$':>8}{'PF':>6}"
          f"{'tot$':>9}{'maxDD$':>8}{'Sharpe':>8}{'ret%':>7}")
