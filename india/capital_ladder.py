# india/capital_ladder.py
"""
AEGIS — CAPITAL LADDER (Future 3 / AEGIS OS building block).

How many stocks should you hold at each capital level, and what does each rung actually deliver?
We backtest the champion (HRP + regime + sector<=2, quarterly) at every position count and map it
to a capital rung, in PLAIN MONEY (profit per month on that capital).

  Rs 50K  -> 3 stocks      Rs 5L  -> 8 stocks      Rs 25L -> 20 stocks
  Rs 1L   -> 5 stocks      Rs 10L -> 15 stocks      Rs 1Cr -> 25 stocks

Run: python india/capital_ladder.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats

LADDER = [(50_000, 3), (1_00_000, 5), (5_00_000, 8),
          (10_00_000, 15), (25_00_000, 20), (1_00_00_000, 25)]


def rupees(n):
    """Indian-style short money label."""
    if n >= 1_00_00_000: return f"Rs{n/1_00_00_000:.0f}Cr"
    if n >= 1_00_000:    return f"Rs{n/1_00_000:.0f}L"
    return f"Rs{n/1000:.0f}K"


def main():
    print("=" * 84)
    print("  AEGIS CAPITAL LADDER — how many stocks per capital, and the money it makes")
    print("  (champion: HRP + regime + sector<=2, quarterly; net of cost; ~5.5y)")
    print("=" * 84)
    print(f"  {'capital':<10}{'stocks':>7}{'avg/yr':>9}{'worst fall':>12}{'worst month':>13}"
          f"{'typical month (Rs)':>21}")
    _, idx = backtest(method="ew")
    for cap, n in LADDER:
        net, _ = backtest(method="hrp", regime="global", topn=n, sector_cap=2, rebal=63)
        net = net.dropna()
        s = stats(net, idx)
        m = (1 + net).resample("ME").prod() - 1
        avg_m = m.mean()
        worst_m = m.min()
        print(f"  {rupees(cap):<10}{n:>7}{s['cagr']:>8.1f}%{s['dd']:>11.1f}%{100*worst_m:>12.1f}%"
              f"{cap*avg_m:>+20,.0f}")
    print("\n  Reading it:")
    print("  - Fewer stocks (small capital) = bumpier ride, bigger worst-fall — concentration risk.")
    print("  - More stocks (large capital)  = steadier, but you need the capital to buy whole shares.")
    print("  - 'typical month (Rs)' = average monthly profit ON THAT capital in normal times.")
    print("  - All survivorship-inflated; the DROP in worst-fall as stocks rise is the honest signal.")


if __name__ == "__main__":
    main()
