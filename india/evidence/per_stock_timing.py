# india/research/per_stock_timing.py
"""
THE USER'S SHARPER IDEA, TESTED:
"For a named stock like SBI, can the engine say 'it will fall next month, so SKIP it for a month'?"

This is a per-stock TIMING filter. We test the most powerful, time-tested timing signal there is —
TREND (is the stock above its 200-day average / in an uptrend?). If ANY simple 'reason' can tell you
when to skip a stock, trend is it. Two honest measures, per stock:

  1) ACCURACY: when the signal says 'skip' (downtrend), how often is next month ACTUALLY down?
     (and when it says 'hold', how often is next month up?)  ~50% = the signal is guessing.
  2) DOES IT PAY: 'hold only in uptrend, else sit in cash' vs simply BUY-AND-HOLD —
     total profit and worst fall. If timing worked, it should make more and/or fall less.

Run: python india/research/per_stock_timing.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.feature_engine import load_panels

STOCKS = ["SBIN", "RELIANCE", "INFY", "ITC", "HDFCBANK", "TATASTEEL"]


def main():
    closes, *_ = load_panels()
    print("=" * 72)
    print("  CAN A 'REASON' TELL YOU TO SKIP A STOCK NEXT MONTH?  (trend-timing test)")
    print("=" * 72)
    print(f"  {'stock':<11}{'signal hit%':>12}{'buy&hold':>11}{'timed':>9}{'B&H fall':>10}{'timed fall':>12}")
    for s in STOCKS:
        c = closes[s].dropna()
        if len(c) < 400:
            continue
        ma200 = c.rolling(200).mean()
        uptrend = (c > ma200)                                  # the "reason" to hold; below = "skip"
        fwd = c.shift(-21) / c - 1                             # next-month return
        d = pd.DataFrame({"up": uptrend, "fwd": fwd}).dropna()
        # 1) accuracy: signal says hold(up) -> month positive?  signal says skip(down) -> month negative?
        hold_ok = (d[d.up]["fwd"] > 0).mean()
        skip_ok = (d[~d.up]["fwd"] < 0).mean()
        n_hold, n_skip = d.up.sum(), (~d.up).sum()
        hit = 100 * (d.up == (d.fwd > 0)).mean()               # overall: did signal match outcome?
        # 2) does it pay: daily returns, timed = in market only when yesterday was uptrend
        ret = c.pct_change().fillna(0)
        timed = ret * uptrend.shift(1).fillna(False)
        bh_tot = 100 * (c.iloc[-1] / c.iloc[0] - 1)
        tm_tot = 100 * ((1 + timed).prod() - 1)
        def dd(series_cum): return 100 * ((series_cum.cummax() - series_cum) / series_cum.cummax()).max()
        bh_dd = dd(c / c.iloc[0])
        tm_dd = dd((1 + timed).cumprod())
        print(f"  {s:<11}{hit:>11.0f}%{bh_tot:>+10.0f}%{tm_tot:>+9.0f}%{bh_dd:>9.0f}%{tm_dd:>11.0f}%")
    print("\n  signal hit% = how often the trend signal matched next month's actual up/down")
    print("  (50% = a coin). 'timed' = skip the stock whenever it's in a downtrend.")
    print("  If timing worked, 'timed' profit should beat 'buy&hold' AND/OR fall less.")


if __name__ == "__main__":
    main()
