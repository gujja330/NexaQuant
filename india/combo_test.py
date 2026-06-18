# india/combo_test.py
"""
COMBINATION TESTER — sweep many India-engine configs and rank them, to find the most
DEPENDABLE setup (not the one flattered by the 2021 bull). Tests factor blends x regime
filter x vol-target x top-N, net of Indian costs, and ranks by a robustness-weighted score
(Sharpe + share of profitable years - drawdown penalty), then prints the winner's per-year.

Run: python india/combo_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import backtest, stats

# --- the combinations to try -------------------------------------------------
W = {
    "mom only":            {"momentum": 1.0},
    "mom+lowvol":          {"momentum": 0.6, "low_vol": 0.4},
    "mom+trend":           {"momentum": 0.6, "trend": 0.4},
    "mom+lowvol+trend":    {"momentum": 0.5, "low_vol": 0.25, "trend": 0.25},
    "lowvol+trend":        {"low_vol": 0.5, "trend": 0.5},
}
CONFIGS = []
for wname, w in W.items():
    for regime in (False, True):
        for vt in (0.0, 0.15):
            CONFIGS.append(dict(name=f"{wname} | regime={'on' if regime else 'off'} | vt={vt or 'off'}",
                                weights=w, topn=5, rebal=5, regime=regime, regime_ma=200, vol_target=vt))


def robustness(s):
    # reward Sharpe + consistency, penalise drawdown — favour DEPENDABLE over lucky
    return s["sharpe"] + (s["pos_years"] / max(s["years"], 1)) - s["dd"] / 100.0


rows = []
for c in CONFIGS:
    s = stats(backtest(c))
    rows.append((c["name"], s, robustness(s)))
rows.sort(key=lambda r: r[2], reverse=True)

print("=" * 96)
print("  INDIA combination sweep — ranked by robustness (Sharpe + %positive-yrs - DD penalty)")
print("=" * 96)
print(f"  {'config':<44}{'tot%':>7}{'CAGR~':>7}{'DD%':>7}{'Sharpe':>8}{'pos yrs':>9}{'worst%':>8}")
for name, s, score in rows:
    cagr = ((1 + s["total"] / 100) ** (1 / max(s["years"], 1)) - 1) * 100
    print(f"  {name:<44}{s['total']:>7.0f}{cagr:>7.1f}{s['dd']:>7.1f}{s['sharpe']:>8.2f}"
          f"{s['pos_years']:>4}/{s['years']:<4}{s['worst_year']:>8.1f}")

print("\n  >>> BEST (most dependable) config:")
best_name, best_s, _ = rows[0]
print(f"      {best_name}")
print(f"      total {best_s['total']:.0f}%  Sharpe {best_s['sharpe']:.2f}  maxDD {best_s['dd']:.1f}%  "
      f"profitable yrs {best_s['pos_years']}/{best_s['years']}")
print(f"      {'year':<6}{'return%':>9}")
for y, r in best_s["yearly"]:
    print(f"      {y:<6}{r:>9.1f}")
