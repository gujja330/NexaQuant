# india/research/mom_breakdown.py
"""
MONTH-ON-MONTH (MoM) breakdown + PICK-QUALITY honesty check.

Two things the user asked for:
  1. MoM returns of the champion vs Nifty (monthly P&L, monthly win rate, beats-index rate).
  2. The real read on "are we picking GOOD stocks?" — across every pick in the last 4 quarters:
     hit rate, average winner vs average loser, PAYOFF ratio, PROFIT FACTOR, expectancy.
     (Hit rate alone is the wrong lens; asymmetry is what makes a 55% hit rate profitable.)

Run: python india/research/mom_breakdown.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, select_names, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import sector_of

REBAL, TOPN, SECTOR_CAP = 63, 15, 2


def mom_table(net, idx, months=18):
    """Monthly returns of strategy vs Nifty."""
    m = (1 + net).resample("ME").prod() - 1
    nf = idx.pct_change().reindex(net.index).fillna(0.0)
    mn = (1 + nf).resample("ME").prod() - 1
    df = pd.DataFrame({"arjuna": 100 * m, "nifty": 100 * mn}).dropna().tail(months)
    return df


def pick_returns():
    """Every stock pick over the last 4 complete quarters and its quarter return."""
    closes, *_ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    rb = list(closes.index[::REBAL])
    pairs = [(rb[i], rb[i + 1]) for i in range(len(rb) - 1)][-4:]
    out = []
    for start, end in pairs:
        hist = rets.loc[:start].tail(LOOKBACK).dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        sel = select_names(hist, TOPN, sector_cap=SECTOR_CAP)
        for s in sel:
            p0, p1 = closes.loc[start, s], closes.loc[end, s]
            if pd.notna(p0) and pd.notna(p1):
                out.append(100 * (p1 / p0 - 1))
    return np.array(out)


def main():
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna()

    print("=" * 64)
    print("  AEGIS v2.1 — MONTH-ON-MONTH (MoM) BREAKDOWN")
    print("=" * 64)
    df = mom_table(net, idx, months=18)
    print(f"  {'month':<10}{'AEGIS':>9}{'Nifty':>9}{'edge':>8}{'result':>10}")
    wins = beats = 0
    for dt, r in df.iterrows():
        edge = r["arjuna"] - r["nifty"]
        res = "UP" if r["arjuna"] > 0 else "down"
        wins += r["arjuna"] > 0; beats += edge > 0
        print(f"  {dt.strftime('%Y-%m'):<10}{r['arjuna']:>+8.2f}%{r['nifty']:>+8.2f}%{edge:>+7.2f}%{res:>10}")
    n = len(df)
    print(f"  {'-'*46}")
    print(f"  months positive   {int(wins)}/{n} = {100*wins/n:.0f}%")
    print(f"  months beat Nifty {int(beats)}/{n} = {100*beats/n:.0f}%")
    print(f"  cum (18m)  AEGIS {100*((1+df['arjuna']/100).prod()-1):+.1f}%   "
          f"Nifty {100*((1+df['nifty']/100).prod()-1):+.1f}%")

    # ---- pick quality ----
    r = pick_returns()
    w = r[r > 0]; l = r[r <= 0]
    payoff = w.mean() / abs(l.mean())
    pf = w.sum() / abs(l.sum())
    exp = r.mean()
    # break-even hit rate given THIS payoff
    be = 1 / (1 + payoff)
    print("\n" + "=" * 64)
    print("  ARE WE PICKING GOOD STOCKS? — 60 picks, last 4 quarters")
    print("=" * 64)
    print(f"  hit rate (winners)     {len(w)}/{len(r)} = {100*len(w)/len(r):.0f}%")
    print(f"  average WINNER         {w.mean():+.1f}%")
    print(f"  average LOSER          {l.mean():+.1f}%")
    print(f"  payoff ratio (win/loss){payoff:>6.2f}  (winner is {payoff:.1f}x the size of a loser)")
    print(f"  profit factor          {pf:>6.2f}  (>1 = profitable; total won / total lost)")
    print(f"  expectancy per pick    {exp:+.2f}%  (avg outcome of any single pick)")
    print(f"  break-even hit rate    {100*be:.0f}%  (with this payoff, you only NEED this many winners)")
    print(f"\n  Verdict: {'PROFITABLE selection — payoff covers the miss rate.' if pf>1 else 'WEAK — losers outweigh winners.'}")
    print("  Hit rate ~55-60% is normal for equity. Demanding 80% (8/10) is not achievable by")
    print("  anyone sustainably — we proved direction is ~coin-flip (AUC 0.50, 13 models). Edge")
    print("  comes from PAYOFF + SIZING, not from being right most of the time.")


if __name__ == "__main__":
    main()
