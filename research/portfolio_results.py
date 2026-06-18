# research/portfolio_results.py
"""
THE CONSISTENCY ENGINE — multi-edge portfolio vs the single-edge baseline.

Shows, per year and over the last 3 years, the combined equal-risk portfolio of all validated
(edge x instrument) sleeves, next to the BTCUSD-trend-only baseline, so the diversification
gain (more positive years, higher Sharpe, lower drawdown) is visible and honest.

Run: python research/portfolio_results.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy.portfolio import sleeves_from_config, combine_equal_risk, per_year


def show(name, rets):
    eq = (1 + rets).cumprod(); peak = eq.cummax()
    tot = 100 * (eq.iloc[-1] - 1); dd = 100 * ((peak - eq) / peak).max()
    sh = rets.mean() / (rets.std() + 1e-12) * np.sqrt(252)
    rows = per_year(rets)
    pos = sum(1 for _, r, _, _ in rows if r > 0)
    print(f"\n  {name}")
    print(f"    {'year':<6}{'return%':>9}{'maxDD%':>8}{'Sharpe':>8}")
    for y, r, d, s in rows:
        print(f"    {y:<6}{r:>9.1f}{d:>7.1f}%{s:>8.2f}")
    last3 = rows[-3:]
    comp = np.prod([1 + r / 100 for _, r, _, _ in last3]) - 1 if last3 else 0
    print(f"    {'-'*30}")
    print(f"    FULL: {tot:+.1f}%  maxDD {dd:.1f}%  Sharpe {sh:.2f}  | profitable yrs {pos}/{len(rows)}")
    print(f"    LAST 3Y: {100*comp:+.1f}% compounded  (avg {np.mean([r for _,r,_,_ in last3]):+.1f}%/yr)")


sleeves = sleeves_from_config()
print("=" * 70)
print("  NexaQuant MULTI-EDGE PORTFOLIO — sleeves:", ", ".join(sleeves.keys()))
print("=" * 70)

# baseline: single edge, single instrument
base = sleeves.get("trend:BTCUSDm")
if base is not None:
    show("BASELINE — trend:BTCUSDm only (single edge)", base)

# the consistency engine: all validated sleeves, equal-risk
port = combine_equal_risk(sleeves)
show("PORTFOLIO — all sleeves, equal-risk (the consistency engine)", port)

# per-sleeve correlation matrix (proof of diversification)
panel = pd.DataFrame(sleeves).sort_index().fillna(0.0)
print("\n  Sleeve correlation matrix (low off-diagonal = good diversification):")
corr = panel.corr()
print(corr.round(2).to_string())
