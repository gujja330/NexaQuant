# india/arjuna_monthly_report.py
"""
MONTH-ON-MONTH results for the dynamic monthly basket (top-30, drop-the-weak, reject weak
fundamentals, VIX de-risk) on Nifty-200, net of cost. Shows every month's return + running Rs,
next to the Nifty, so you can see month by month how it behaves.

Run: python india/arjuna_monthly_report.py            # the drop-weak top-30 strategy
     python india/arjuna_monthly_report.py --own-all   # the own-everything baseline
"""
import argparse, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.arjuna_strategy import backtest
from india.arjuna_compare import NIFTY200


def monthly(net, idx):
    nifty = idx.pct_change().fillna(0.0)
    m = pd.DataFrame({"strat": net, "nifty": nifty})
    g = m.groupby([net.index.year, net.index.month]).apply(lambda x: (1 + x).prod() - 1)
    return g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--own-all", action="store_true")
    ap.add_argument("--years", nargs="+", type=int, default=None,
                    help="show only these years, each rebased to Rs1,00,000")
    a = ap.parse_args()
    if a.own_all:
        net, idx, _, _ = backtest("all", rebal=21, universe=NIFTY200)
        label = "OWN-ALL ~200 (equal weight, monthly)"
    else:
        net, idx, _, _ = backtest("quality", k=30, rebal=21, reject_weak=True, vix_derisk=True, universe=NIFTY200)
        label = "DROP-THE-WEAK top-30 (monthly, reject weak, VIX de-risk)"

    g = monthly(net, idx)
    print("=" * 64)
    print(f"  MONTH-ON-MONTH — {label}  (Nifty-200, net of cost)")
    print("=" * 64)
    if a.years:
        for yr in a.years:
            print(f"\n  --- {yr} (rebased to Rs1,00,000) ---")
            print(f"  {'month':<9}{'strat%':>9}{'nifty%':>9}{'edge':>8}{'balance_Rs':>14}")
            bal = 100000.0; sret = 1.0; nret = 1.0
            for (y, mth), row in g.iterrows():
                if y != yr:
                    continue
                sr, ny = row["strat"], row["nifty"]
                bal *= (1 + sr); sret *= (1 + sr); nret *= (1 + ny)
                print(f"  {y}-{mth:02d}{100*sr:>9.1f}{100*ny:>9.1f}{100*(sr-ny):>+8.1f}{bal:>14,.0f}")
            print(f"  => {yr}: strat {100*(sret-1):+.1f}%   nifty {100*(nret-1):+.1f}%   Rs1L -> Rs{bal:,.0f}")
    else:
        print(f"  {'month':<9}{'strat%':>9}{'nifty%':>9}{'edge':>8}{'balance_Rs':>14}")
        bal = 100000.0; wins = 0; n = 0
        for (y, mth), row in g.iterrows():
            sr, ny = row["strat"], row["nifty"]
            if sr == 0 and bal == 100000.0:
                continue
            bal *= (1 + sr); n += 1; wins += sr > ny
            print(f"  {y}-{mth:02d}{100*sr:>9.1f}{100*ny:>9.1f}{100*(sr-ny):>+8.1f}{bal:>14,.0f}")
        tot = bal / 100000 - 1; yrs = len(net) / 252
        print("  " + "-" * 55)
        print(f"  months: {n}   beating Nifty: {wins} ({100*wins/max(n,1):.0f}%)")
        print(f"  TOTAL {100*tot:+.0f}%   CAGR {100*((1+tot)**(1/yrs)-1):.1f}%/yr   Rs1L -> Rs{bal:,.0f}")
    print("\n  (survivorship-inflated; forward paper run is the clean test)")
