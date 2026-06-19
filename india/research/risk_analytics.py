# india/research/risk_analytics.py
"""
RISK ANALYTICS (final Phase-2 diagnostics, no models) for Core v2.1:
  1. Recovery analysis (time to climb back from drawdowns)
  2. Underwater curve (depth + duration of drawdown periods; saved PNG)
  3. Tail risk (VaR / CVaR / worst 1% & 5% / expected shortfall)
  4. Probability engine (Monte Carlo: P(CAGR>8/10/12/15%), P(DD>15/20%))

Run: python india/research/risk_analytics.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest
from india.research.monte_carlo import sim

CFG = dict(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
OUT = Path(__file__).resolve().parents[2] / "output"


def main():
    net, idx = backtest(**CFG)
    net = net.dropna()
    eq = (1 + net).cumprod(); peak = eq.cummax(); uw = eq / peak - 1

    print("=" * 64); print("  ARJUNA v2.1 — RISK ANALYTICS"); print("=" * 64)

    # 1) recovery episodes (peak -> back to new high)
    is_high = uw >= -1e-9; episodes = []; last = 0
    for i in range(1, len(uw)):
        if is_high.iloc[i]:
            if i - last > 1:
                seg = uw.iloc[last:i + 1]; episodes.append((len(seg), 100 * seg.min(), True))
            last = i
    if not is_high.iloc[-1]:
        seg = uw.iloc[last:]; episodes.append((len(seg), 100 * seg.min(), False))
    rec = [d for d, depth, done in episodes if done]
    print(f"\n  1) RECOVERY (from drawdown to new high): {len(episodes)} episodes")
    if rec:
        print(f"     recovery time (trading days)  median {int(np.median(rec))} (~{np.median(rec)/21:.1f} mo)  "
              f"avg {int(np.mean(rec))}  max {max(rec)} (~{max(rec)/21:.1f} mo)")
    ongoing = [(d, depth) for d, depth, done in episodes if not done]
    if ongoing:
        print(f"     currently underwater: {ongoing[0][0]} days, depth {ongoing[0][1]:.1f}%")

    # 2) underwater curve
    longest = max((d for d, _, _ in episodes), default=0)
    print(f"\n  2) UNDERWATER: max depth {100*uw.min():.1f}%   longest underwater {longest} days (~{longest/21:.1f} mo)")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.fill_between(uw.index, 100 * uw.values, 0, color="#d62246", alpha=0.6)
    ax.set_title("ARJUNA v2.1 — Underwater Curve (drawdown over time)", weight="bold")
    ax.set_ylabel("drawdown %"); ax.grid(alpha=0.3)
    for s in ["top", "right"]: ax.spines[s].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "arjuna_underwater.png", dpi=110); plt.close(fig)
    print(f"     underwater curve saved -> output/arjuna_underwater.png")

    # 3) tail risk (daily + monthly)
    r = net.values
    var95, var99 = np.percentile(r, 5), np.percentile(r, 1)
    cvar95 = r[r <= var95].mean(); cvar99 = r[r <= var99].mean()
    monthly = (1 + net).groupby(np.arange(len(net)) // 21).prod() - 1
    print(f"\n  3) TAIL RISK:")
    print(f"     daily  VaR95 {100*var95:.2f}%  CVaR95 {100*cvar95:.2f}%  VaR99 {100*var99:.2f}%  "
          f"worst day {100*r.min():.2f}%")
    print(f"     monthly worst {100*monthly.min():.1f}%  ·  5%-worst months avg {100*monthly[monthly<=monthly.quantile(0.05)].mean():.1f}%")

    # 4) probability engine
    c, d = sim(net, 252, 0.65)
    print(f"\n  4) PROBABILITY ENGINE (Monte Carlo, 1yr, 35% haircut):")
    for thr in (8, 10, 12, 15):
        print(f"     P(CAGR > {thr}%) = {100*(c > thr/100).mean():.0f}%")
    print(f"     P(maxDD > 15%) = {100*(d > 0.15).mean():.0f}%   P(maxDD > 20%) = {100*(d > 0.20).mean():.0f}%")
    print("\n  (Survivorship-inflated; the shapes — recovery speed, tail, P-bands — are the honest signal.)")


if __name__ == "__main__":
    main()
