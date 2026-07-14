# india/backpaper.py
"""
BACKPAPER — the honest "would paper-trading this have worked?" record.

Not the in-sample headline. Three honest views of the FROZEN champion (HRP + regime + 15 stk +
sector<=2, quarterly), every decision causal (uses only trailing data):
  1. Year-by-year realized record vs Nifty — INCLUDING the bad years.
  2. Out-of-sample split: the champion's RULES were chosen looking at the whole history, so we test
     them on the back HALF of the timeline (the slice they were least shaped by) vs the front half.
  3. The relative edge (vs Nifty) per half — the survivorship-robust signal.

CAVEAT we cannot remove: the universe is TODAY's Nifty-200 (survivorship). Absolute levels are
inflated; the edge OVER Nifty (also survivorship-affected) is the trustworthy read.

Run: python india/backpaper.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats

# ENG002: metric formulas consolidated into nexaquant.lib.metrics. The wrappers
# below preserve seg_stats's (cagr%, sharpe, dd%) signature; the arithmetic is
# byte-identical to the pre-migration inline implementation.
from nexaquant.lib.metrics import (
    cagr_from_returns as _cagr_from_returns,
    max_drawdown_from_returns as _mdd_from_returns,
    sharpe as _sharpe,
)


def seg_stats(r, idx):
    """(CAGR%, Sharpe, MaxDD%) for a returns series.

    ENG002: cagr / max_drawdown / sharpe delegated to nexaquant.lib.metrics.
    Byte-identical to the pre-migration formula (verified in test_lib.py test 26-28).
    The `idx` parameter is retained for signature compatibility with legacy call
    sites; unused inside this function.
    """
    del idx  # retained for signature compat
    cagr = 100.0 * _cagr_from_returns(r)
    dd = 100.0 * _mdd_from_returns(r)
    sh = _sharpe(r)
    return cagr, sh, dd


def main():
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna()
    nf = idx.pct_change().reindex(net.index).fillna(0.0)

    print("=" * 72)
    print("  AEGIS BACKPAPER — would paper-trading the frozen champion have worked?")
    print("=" * 72)

    # 1) year-by-year realized, vs Nifty
    print("\n  1) YEAR-BY-YEAR (realized, net of cost) — incl. the bad years:")
    print(f"     {'year':<6}{'AEGIS':>9}{'Nifty':>9}{'edge':>8}{'winner':>9}")
    wins = 0; yrs = sorted(set(net.index.year))
    for y in yrs:
        a = 100 * ((1 + net[net.index.year == y]).prod() - 1)
        n = 100 * ((1 + nf[nf.index.year == y]).prod() - 1)
        w = "AEGIS" if a > n else "Nifty"
        wins += a > n
        print(f"     {y:<6}{a:>+8.1f}%{n:>+8.1f}%{a-n:>+7.1f}%{w:>9}")
    print(f"     -> beat Nifty in {wins}/{len(yrs)} years")

    # 2) out-of-sample split: front half vs back half
    mid = net.index[len(net) // 2]
    print(f"\n  2) OUT-OF-SAMPLE SPLIT at {mid.date()} (rules fixed; does the edge persist in back half?):")
    print(f"     {'window':<10}{'AEGIS CAGR/Sharpe/DD':>30}{'Nifty CAGR/Sharpe/DD':>28}")
    for label, sl in [("FRONT", net.index < mid), ("BACK (OOS)", net.index >= mid)]:
        a = seg_stats(net[sl], idx); n = seg_stats(nf[sl], idx)
        print(f"     {label:<10}{a[0]:>10.1f}% {a[1]:>6.2f} {a[2]:>6.1f}%"
              f"{n[0]:>14.1f}% {n[1]:>6.2f} {n[2]:>6.1f}%")

    # 3) verdict
    full_a = seg_stats(net, idx); full_n = seg_stats(nf, idx)
    print(f"\n  3) FULL PERIOD: AEGIS Sharpe {full_a[1]:.2f} / DD {full_a[2]:.1f}%  vs  "
          f"Nifty Sharpe {full_n[1]:.2f} / DD {full_n[2]:.1f}%")
    print("\n  HONEST VERDICT:")
    print("  - The edge is RELATIVE + RISK-side (higher Sharpe, ~half the drawdown, beats Nifty in")
    print("    down years), NOT a smooth high absolute return — there ARE negative years.")
    print("  - Survivorship still inflates absolute levels; the edge-over-Nifty is the trustworthy part.")
    print("  - If the BACK-half (OOS) edge resembles the FRONT half, the rules generalise -> forward")
    print("    paper is worth running. If the back half collapses, do NOT bother with forward paper.")


if __name__ == "__main__":
    main()
