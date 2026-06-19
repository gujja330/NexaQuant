# india/arjuna_yearly.py
"""
PER-YEAR validated results for the DYNAMIC MONTHLY basket (your spec):
  hold ~1 month, each cycle DROP the non-performers (low tech+fundamental score) and ADD fresh
  top names, equal-weight, reject weak fundamentals, VIX de-risk. Nifty-200 universe, net of cost.

Shows year-by-year Rs gains + average annual return, and whether 'drop the weak' beats owning
everything and beats the Nifty. (News filter is LIVE/forward only -> not in this historical test.)

Run: python india/arjuna_yearly.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from india.arjuna_strategy import backtest
from india.data_nse import NIFTY200

U = NIFTY200


def per_year(net, idx, label):
    nifty = idx.pct_change().fillna(0.0)
    eq = (1 + net).cumprod(); peak = eq.cummax()
    print(f"\n  {label}")
    print(f"  {'year':<6}{'strat%':>9}{'nifty%':>9}{'edge':>8}{'start_Rs':>13}{'end_Rs':>13}{'gain_Rs':>13}")
    comp = 100000.0; yrly = []
    for y, g in net.groupby(net.index.year):
        if len(g) < 20:
            continue
        sr = (1 + g).prod() - 1; ny = (1 + nifty.reindex(g.index).fillna(0)).prod() - 1
        start = comp; comp *= (1 + sr); yrly.append(sr)
        print(f"  {y:<6}{100*sr:>9.1f}{100*ny:>9.1f}{100*(sr-ny):>+8.1f}{start:>13,.0f}{comp:>13,.0f}{comp-start:>+13,.0f}")
    yrs = len(net) / 252
    cagr = (eq.iloc[-1]) ** (1 / yrs) - 1
    sh = net.mean() / (net.std() + 1e-12) * np.sqrt(252)
    print(f"  {'-'*65}")
    print(f"  AVERAGE/yr (CAGR) {100*cagr:>5.1f}%   mean yearly {100*np.mean(yrly):>5.1f}%   "
          f"Sharpe {sh:.2f}   maxDD {100*((peak-eq)/peak).max():.1f}%")
    print(f"  Rs1,00,000 -> Rs{eq.iloc[-1]*1e5:,.0f} over {yrs:.1f} years")
    return cagr


if __name__ == "__main__":
    print("=" * 78)
    print("  PER-YEAR VALIDATION — dynamic MONTHLY basket, Nifty-200, net of cost (~5.5y)")
    print("=" * 78)

    # 1) own everything (no selection) -- the baseline
    net0, idx, _, _ = backtest("all", rebal=21, universe=U)
    per_year(net0, idx, "A) EW-ALL ~200 (own everything, monthly) -- baseline")

    # 2) YOUR strategy: monthly, keep top-30, DROP the weak + reject weak fundamentals + VIX
    net1, idx, _, _ = backtest("quality", k=30, rebal=21, reject_weak=True, vix_derisk=True, universe=U)
    per_year(net1, idx, "B) DROP-THE-WEAK: monthly top-30 (tech+fund), reject weak, VIX de-risk")

    # 3) tighter: top-15 (more concentrated drop-weak)
    net2, idx, _, _ = backtest("quality", k=15, rebal=21, reject_weak=True, vix_derisk=True, universe=U)
    per_year(net2, idx, "C) DROP-THE-WEAK tighter: monthly top-15")

    print("\n  NOTE: survivorship bias inflates absolutes (today's Nifty-200 members); the EDGE column")
    print("        (strat minus Nifty) and the A-vs-B comparison are the honest signal.")
