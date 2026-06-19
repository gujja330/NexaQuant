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
    print("=" * 64)
    print("  MONTE CARLO — Core v2.1 (10,000 paths, drift haircut 35% for honesty)")
    print("=" * 64)
    for label, h in [("1 year", 252), ("3 years", 756)]:
        c, d = sim(net.dropna(), h)
        print(f"\n  {label}:")
        print(f"    median CAGR {100*np.median(c):+.1f}%   "
              f"P(CAGR>12%) {100*(c>0.12).mean():.0f}%   P(CAGR>0) {100*(c>0).mean():.0f}%")
        print(f"    worst 5% CAGR {100*np.percentile(c,5):+.1f}%   "
              f"P(maxDD>20%) {100*(d>0.20).mean():.0f}%   typical maxDD {100*np.median(d):.0f}%")
    print("\n  Read: honest forward odds. Median ~realistic; the worst-5% and P(DD>20%) are the risk.")


if __name__ == "__main__":
    main()
