# india/picker_log.py
"""
Trade log for the GOOD strategy — the momentum+low-vol PICKER (the one worth running),
shown the honest way: COMPOUNDED portfolio growth on real capital, plus a holding-by-holding
log (which stock entered the top-5, when it exited, days held, % return, Rs P&L) and a yearly
wins-vs-losses + net table. Contrast with the weak per-stock blotter (india/trade_blotter.py).

Config = the combo-sweep winner: momentum 0.6 + low_vol 0.4, top-5, weekly rebalance, no
regime filter, no vol-target. Net of ~21 bps Indian costs.

Run: python india/picker_log.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import load, composite_score, COST_BPS

START_CAPITAL = 100000.0          # Rs 1,00,000 illustrative portfolio
TOPN, REBAL = 5, 5
WEIGHTS = {"momentum": 0.6, "low_vol": 0.4}

closes, _ = load()
rets = closes.pct_change().fillna(0.0)
score = composite_score(closes, WEIGHTS)

# weekly top-5 equal-weight target weights
w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
for dt, row in score.iterrows():
    r = row.dropna()
    if len(r) < TOPN:
        continue
    w.loc[dt, r.sort_values(ascending=False).index[:TOPN]] = 1.0 / TOPN
mask = np.zeros(len(closes), dtype=bool); mask[::REBAL] = True
w[~mask] = np.nan; w = w.ffill().fillna(0.0)

# ---- compounded portfolio (the REAL performance) ----
port = (w.shift(1) * rets).sum(axis=1) - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
eq = (1 + port).cumprod() * START_CAPITAL

print("=" * 68)
print("  PICKER (momentum+low-vol, top-5 weekly) — COMPOUNDED, net of cost")
print("=" * 68)
print(f"  {'year':<6}{'return%':>9}{'end_value_Rs':>15}")
comp = START_CAPITAL
for y, g in port.groupby(port.index.year):
    if len(g) < 30:
        continue
    yr_ret = (1 + g).prod() - 1
    comp *= (1 + yr_ret)
    print(f"  {y:<6}{100*yr_ret:>9.1f}{comp:>15,.0f}")
print(f"  {'-'*30}")
print(f"  START Rs {START_CAPITAL:,.0f}  ->  END Rs {eq.iloc[-1]:,.0f}   "
      f"({100*(eq.iloc[-1]/START_CAPITAL-1):+.0f}% total, {len(set(port.index.year))}y)")
peak = eq.cummax()
print(f"  maxDD {100*((peak-eq)/peak).max():.1f}%   Sharpe {port.mean()/(port.std()+1e-12)*np.sqrt(252):.2f}")

# ---- holding-by-holding log (when each name was in the top-5) ----
held = w > 0
rows = []
for s in closes.columns:
    inpos = held[s].values; idx = closes.index
    i = 0
    while i < len(inpos):
        if inpos[i]:
            j = i
            while j + 1 < len(inpos) and inpos[j + 1]:
                j += 1
            e_px, x_px = closes[s].iloc[i], closes[s].iloc[j]
            rows.append({"stock": s, "in_date": idx[i].date(), "out_date": idx[j].date(),
                         "days_held": (idx[j] - idx[i]).days, "entry_px": round(e_px, 1),
                         "exit_px": round(x_px, 1), "ret_pct": round(100 * (x_px / e_px - 1), 2),
                         "win": x_px > e_px, "year": idx[i].year})
            i = j + 1
        else:
            i += 1
log = pd.DataFrame(rows)
OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)
log.to_csv(OUT / "india_picker_log.csv", index=False)

print("\n  HOLDING-BY-HOLDING yearly (each = one stock's stint in the top-5):")
print(f"  {'year':<6}{'holdings':>9}{'WINS':>6}{'LOSSES':>8}{'win%':>6}{'avg_days':>9}{'avg_ret%':>9}")
for y, d in log.groupby("year"):
    w_ = int(d["win"].sum()); l_ = int((~d["win"]).sum())
    print(f"  {y:<6}{len(d):>9}{w_:>6}{l_:>8}{100*d['win'].mean():>5.0f}%{d['days_held'].mean():>9.0f}{d['ret_pct'].mean():>9.1f}")
print(f"\n  full holding log -> output/india_picker_log.csv  ({len(log)} holdings)")
print("  NOTE: this is the strategy worth running. The per-stock trend/breakout blotter is dropped.")
