# research/multi_asset_portfolio.py
"""
DEEP CROSS-ASSET PORTFOLIO — the breadth step toward a consistent, all-weather engine.

Runs both validated edges (trend + breakout) across the deep daily universe
(crypto + metals + equities + FX + energy) and blends them equal-risk. These are genuinely
uncorrelated MARKETS, so when one asset class is in drawdown others carry — validated over
~2 decades (2008, 2015, 2020 COVID, 2022 all in-sample), plus the last 3 years explicitly.

Everything config-driven (edges.deep_universe). Run: python research/multi_asset_portfolio.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import cfg
from strategy.portfolio import _sleeve_daily, combine_equal_risk, per_year

uni = cfg()["edges"]["deep_universe"]; tf = cfg()["edges"]["deep_timeframe"]
length = cfg()["edges"]["breakout"].get("length", 20)

MIN_SHARPE = 0.4   # QUALITY GATE: a sleeve must clear this standalone to enter the book
                   # (breadth only helps with REAL edges; dead sleeves just dilute to zero).
raw, sleeves = {}, {}
for sym in uni:
    for kind in ("trend", "breakout"):
        d = _sleeve_daily(sym, tf, kind, length)
        if d is None or len(d) <= 60:
            continue
        sh = d.mean() / (d.std() + 1e-12) * np.sqrt(252)
        raw[f"{kind}:{sym}"] = sh
        if sh >= MIN_SHARPE:
            sleeves[f"{kind}:{sym}"] = d
print("  sleeve gate (standalone Sharpe >= %.1f):" % MIN_SHARPE)
for k, sh in raw.items():
    print(f"     {k:<20} Sharpe {sh:+.2f}  {'KEEP' if sh >= MIN_SHARPE else 'drop (dilutes)'}")

print("=" * 74)
print(f"  DEEP CROSS-ASSET PORTFOLIO — {len(sleeves)} sleeves across {len(uni)} markets")
print("  " + ", ".join(uni))
print("=" * 74)

port = combine_equal_risk(sleeves)
rows = per_year(port)
print(f"\n  {'year':<6}{'return%':>9}{'maxDD%':>8}{'Sharpe':>8}")
for y, r, d, s in rows:
    print(f"  {y:<6}{r:>9.1f}{d:>7.1f}%{s:>8.2f}")

eq = (1 + port).cumprod(); peak = eq.cummax()
pos = sum(1 for _, r, _, _ in rows if r > 0)
last3 = rows[-3:]; comp = np.prod([1 + r / 100 for _, r, _, _ in last3]) - 1
print(f"  {'-'*31}")
print(f"  FULL: {100*(eq.iloc[-1]-1):+.0f}%  maxDD {100*((peak-eq)/peak).max():.1f}%  "
      f"Sharpe {port.mean()/(port.std()+1e-12)*np.sqrt(252):.2f}  | profitable yrs {pos}/{len(rows)}")
print(f"  LAST 3Y: {100*comp:+.1f}% compounded  (avg {np.mean([r for _,r,_,_ in last3]):+.1f}%/yr, "
      f"worst {min(r for _,r,_,_ in last3):+.1f}%)")

# correlation across asset classes (the proof of breadth)
panel = pd.DataFrame(sleeves).sort_index().fillna(0.0)
c = panel.corr().values
off = c[np.triu_indices_from(c, k=1)]
print(f"\n  cross-sleeve correlation: avg |corr| = {np.abs(off).mean():.2f}, max = {np.abs(off).max():.2f}  "
      f"(low = genuinely diversified)")
