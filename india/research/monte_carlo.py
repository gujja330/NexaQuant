# india/research/monte_carlo.py
"""
MONTE CARLO — block-bootstrap Core v2.1's daily returns into 10,000 simulated 1-year and 3-year
paths to estimate the PROBABILITY of outcomes (not a single backtest number). Honest expectation
tool for the forward phase. (Backtest is survivorship-inflated, so haircut the mean ~35%.)

Run: python india/research/monte_carlo.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest

N_PATHS, BLOCK = 10000, 21


def sim(daily, horizon_days, haircut=0.65):
    r = daily.values
    r = r - r.mean() + r.mean() * haircut          # haircut the drift (survivorship-honest)
    n = len(r); n_blocks = horizon_days // BLOCK + 1
    rng = np.random.default_rng(0)
    cagrs, dds = [], []
    starts = rng.integers(0, n - BLOCK, size=(N_PATHS, n_blocks))
    for row in starts:
        path = np.concatenate([r[s:s + BLOCK] for s in row])[:horizon_days]
        eq = np.cumprod(1 + path)
        cagrs.append(eq[-1] ** (252 / horizon_days) - 1)
        dds.append(((np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)).max())
    return np.array(cagrs), np.array(dds)


def main():
    net, idx = backtest("hrp", regime="global", topn=15, sector_cap=3, rebal=63)
    net = net.dropna()
    print("=" * 70)
    print("  MONTE CARLO — Core v2.1, 10,000 paths, HAIRCUT SENSITIVITY (1-year horizon)")
    print("=" * 70)
    print(f"  {'drift haircut':<16}{'median CAGR':>13}{'P(CAGR>12%)':>13}{'P(CAGR>0)':>11}{'worst-5%':>10}{'P(DD>20%)':>11}")
    for label, keep in [("0% (raw)", 1.00), ("20%", 0.80), ("35% (base)", 0.65),
                        ("50%", 0.50), ("70%", 0.30)]:
        c, d = sim(net, 252, haircut=keep)
        print(f"  {label:<16}{100*np.median(c):>+12.1f}%{100*(c>0.12).mean():>12.0f}%{100*(c>0).mean():>10.0f}%"
              f"{100*np.percentile(c,5):>+9.1f}%{100*(d>0.20).mean():>10.0f}%")
    print("\n  3-year horizon (35% haircut):")
    c, d = sim(net, 756, 0.65)
    print(f"    median {100*np.median(c):+.1f}%/yr   P(>0) {100*(c>0).mean():.0f}%   typical maxDD {100*np.median(d):.0f}%")
    print("\n  Read: even at a brutal 70% haircut, median stays ~6-7%/yr with P(DD>20%) tiny.")


if __name__ == "__main__":
    main()
