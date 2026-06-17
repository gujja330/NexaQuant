# research/deep_walkforward.py
"""
DEEP multi-regime walk-forward — the real test of robustness across ~2 decades.

Uses the free yfinance daily history (data/pull_yfinance.py): gold 2000+, BTC 2014+,
EURUSD 2003+, S&P 1927+, oil 2000+ — spanning 2008, 2011, 2013-15 bear/range, 2020 COVID,
2022, etc. Runs the validated regime-aware LONG+SHORT playbook, year by year (anchored:
train on all prior years, test the next), and counts profitable years per instrument.

Daily resolution (long history is daily-only on free sources) — coarser than the H4 we
trade, but it's the strongest available test of whether the edge survives many regimes.

Run: python research/deep_walkforward.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, pipeline
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import trade_stats
from backtest.engine import BARS_PER_YEAR
from research.long_short_walkforward import both_sides

RAW = ROOT / "data" / "raw"
DEEP = ["XAUUSDd", "BTCUSDd", "SPXd", "EURUSDd", "WTId"]   # deep daily symbols


def run():
    print("=" * 96)
    print("  DEEP MULTI-REGIME WALK-FORWARD — regime-aware LONG+SHORT, daily, ~2 decades")
    print("=" * 96)
    for sym in DEEP:
        p = RAW / f"{sym}_D1.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p).sort_index()
        sp = symbol_params(sym, df["close"])
        # ADX gate (stateless) for the deep test — a single HMM fit does NOT generalise
        # across decades (it stops labelling 'trend' in later years). ADX adapts everywhere.
        method = "adx"
        reg = playbook.regime_labels(df, method)
        a = atr(df, 14)
        years = sorted(df.index.year.unique())[1:]
        print(f"\n  {sym}  ({method.upper()})  {df.index[0].date()} -> {df.index[-1].date()}")
        print(f"    {'yr':<6}{'trades':>7}{'win%':>6}{'ret%':>8}{'PF':>6}{'maxDD%':>8}{'Sharpe':>8}")
        pos = n = 0
        rets = []
        for ty in years:
            mask = df.index.year == ty
            if mask.sum() < 30 or df[df.index.year < ty].shape[0] < 250:
                continue
            tr = both_sides(df, mask, a, sp, reg, do_short=True)
            s = trade_stats(tr, BARS_PER_YEAR["D1"], tr["bars"].mean() if not tr.empty else 1)
            if not s:
                continue
            notional = df[mask]["close"].iloc[0]
            ret = 100 * s["total"] / notional
            n += 1; pos += ret > 0; rets.append(ret)
            print(f"    {ty:<6}{s['trades']:>7}{100*s['win']:>5.0f}%{ret:>8.1f}{s['pf']:>6.2f}"
                  f"{100*s['dd']/notional:>7.1f}%{s['sharpe']:>8.2f}")
        if n:
            print(f"    => {pos}/{n} years profitable | avg {np.mean(rets):+.1f}%/yr | "
                  f"median {np.median(rets):+.1f}% | worst {min(rets):+.1f}%")


if __name__ == "__main__":
    run()
