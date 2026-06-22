# india/short_horizon.py
"""
SHORT-HORIZON EXPECTATIONS — what to realistically expect holding for 1 week .. 1 year.

The honest truth this surfaces: at very short horizons (1 week, 1 month) equity is mostly NOISE —
near a coin flip, wide swings, the risk-management edge has no time to work. The system's value
(high odds of profit, smooth compounding) only shows up from ~6 months out. This table is the
evidence for "give it time", in plain money on Rs 1,00,000.

Run: python india/short_horizon.py
"""
import sys, warnings
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest

CAP = 100000
HORIZONS = [("1 week", 5), ("1 month", 21), ("3 months", 63),
            ("6 months", 126), ("1 year", 252)]


def main():
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna()
    eq = (1 + net).cumprod()
    nf = idx.pct_change().reindex(net.index).fillna(0.0)
    eqn = (1 + nf).cumprod()

    print("=" * 80)
    print("  ARJUNA — WHAT TO EXPECT BY HOLDING PERIOD (on Rs 1,00,000)")
    print("=" * 80)
    print(f"  {'hold':<10}{'odds of profit':>15}{'typical gain':>14}{'good case':>13}{'bad case':>13}{'verdict':>14}")
    for label, h in HORIZONS:
        r = (eq.shift(-h) / eq - 1).dropna()
        if not len(r):
            continue
        p = 100 * (r > 0).mean()
        med = r.median(); p75 = r.quantile(0.75); p05 = r.quantile(0.05)
        verdict = "COIN FLIP" if p < 65 else ("OK" if p < 85 else "STRONG")
        print(f"  {label:<10}{p:>13.0f}%{CAP*med:>+13,.0f}{CAP*p75:>+13,.0f}{CAP*p05:>+13,.0f}{verdict:>14}")

    print("\n  How to read it:")
    print("  - 'odds of profit' = how often you'd END that period in profit (historical).")
    print("  - 'typical gain' = median rupee outcome; 'good/bad case' = 75th / 5th percentile.")
    print("  - 1 week / 1 month are near COIN FLIPS — big swings, no real edge. That's not ARJUNA")
    print("    failing; it's how equities behave short-term. Edge needs ~6-12 months to show up.")
    print("\n  Honest guidance: this product is built for 6 months to 1 year+. For 1 week / 1 month")
    print("  holding, no system (ours or anyone's) can give you reliable profit on stocks.")


if __name__ == "__main__":
    main()
