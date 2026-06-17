# research/streak_test.py
"""
MOMENTUM-CAPTURE test across timeframes: consecutive candle STREAKS + lengthy candles.

Your two insights, made testable:
  * "1,2,3 candles in one direction" -> a STREAK of N same-direction closes = momentum
    ignition. Enter in that direction (only in a trending regime), ride with momentum exit.
  * "lengthy candles carry the pips"  -> require the streak's net move to be a real
    expansion (cumulative body >= k*ATR), not three tiny bars.

Runs on EVERY BTC timeframe present (M5/M15/H1/H4) so we see where momentum capture
actually pays — small TFs are where streaks fire most. Long+short, tiered risk, net cost.

Variants per TF:
  base2  : 2 consecutive candles same dir, in trend regime
  base3  : 3 consecutive candles same dir, in trend regime
  exp2   : 2-streak AND cumulative body >= K*ATR (lengthy)
  exp3   : 3-streak AND cumulative body >= K*ATR (lengthy)

Run: python research/streak_test.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

SYM = "BTCUSDm"
TFS = ["M5", "M15", "H1", "H4"]
K = 1.5      # cumulative streak body must be >= K*ATR to count as "lengthy"


def tier_ret(tr, df):
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    risk = np.where(conf < 1.5, 0.005, np.where(conf < 2.0, 0.01, 0.02))
    eq = np.cumprod(1 + risk * tr["R"].values); peak = np.maximum.accumulate(eq)
    return 100 * (eq[-1] - 1), 100 * np.max((peak - eq) / peak)


def streak_mask(df, n, up):
    """True where the last n candles all closed in the same direction (up or down)."""
    dir_up = (df["close"] > df["open"])
    want = dir_up if up else ~dir_up
    m = want.copy()
    for k in range(1, n):
        m &= want.shift(k, fill_value=False)
    return m


def evaluate(df, sp, tf, n, require_big):
    a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    body = (df["close"] - df["open"]).abs()
    cum_body = body.rolling(n).sum()
    big = cum_body >= K * a
    trend = reg != "range"
    rows = []
    for side, s, up in (("long", 1, True), ("short", -1, False)):
        ent = streak_mask(df, n, up) & trend
        if require_big:
            ent = ent & big
        ent = ent.shift(1, fill_value=False)        # act next bar (no lookahead)
        ex = playbook.momentum_exit_signal(df, side=side)
        rows.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                    pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    tr = pd.concat([p for p in rows if not p.empty]).sort_values("entry_time")
    if tr.empty:
        return None
    st = trade_stats(tr, BARS_PER_YEAR.get(tf, 252 * 24), tr["bars"].mean())
    ret, dd = tier_ret(tr, df)
    return dict(trades=st["trades"], win=100 * st["win"], pf=st["pf"],
                avgpips=tr["pips"].mean(), pips=st["total_pips"], ret=ret, dd=dd)


print(f"MOMENTUM-CAPTURE (streaks + lengthy candles) — {SYM}, long+short, tiered risk")
print(f"  {'TF':<5}{'variant':<8}{'trades':>7}{'win%':>6}{'PF':>6}{'avgpips':>9}{'totpips':>10}{'ret%':>7}{'maxDD%':>8}")
for tf in TFS:
    p = ROOT / f"data/raw/{SYM}_{tf}.parquet"
    if not p.exists():
        print(f"  {tf:<5} (no data yet — pull first)"); continue
    df = pd.read_parquet(p).sort_index()
    sp = symbol_params(SYM, df["close"])
    for label, n, big in (("base2", 2, False), ("base3", 3, False), ("base4", 4, False),
                          ("exp2", 2, True), ("exp3", 3, True), ("exp4", 4, True)):
        r = evaluate(df, sp, tf, n, big)
        if r:
            print(f"  {tf:<5}{label:<8}{int(r['trades']):>7}{r['win']:>5.0f}%{r['pf']:>6.2f}"
                  f"{r['avgpips']:>9.0f}{r['pips']:>10.0f}{r['ret']:>6.0f}%{r['dd']:>7.0f}%")
    print()
