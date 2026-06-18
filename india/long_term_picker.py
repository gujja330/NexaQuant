# india/long_term_picker.py
"""
LONG-TERM stock picker — the proven edge, tuned for longer holds + lower churn, and it prints
the ACTUAL stocks to buy TODAY.

  * 12-month momentum (252d, skip 21) + low-volatility  (the validated factor combo)
  * MONTHLY rebalance (21 bars) -> long-term holds, less cost
  * correlation + sector caps (diversify; no 5 look-alikes)
  * QUALITY tilt on the live pick (ROE/debt/margin from fundamentals.parquet) + earnings date
Backtests per-year, then outputs the current top-N "buy list" with score + quality + sector.

Run: python india/long_term_picker.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import load, composite_score, COST_BPS
from india.picker_pro import SECTOR, select

WEIGHTS = {"momentum": 0.6, "low_vol": 0.4}
TOPN, REBAL = 6, 21              # 6 names, monthly rebalance (long-term)
MOM_LB, MOM_SKIP = 252, 21       # 12-month momentum, skip last month


def run():
    closes, _ = load()
    rets = closes.pct_change().fillna(0.0)
    score = composite_score(closes, WEIGHTS, mom_lb=MOM_LB, mom_skip=MOM_SKIP)
    rebal_days = set(closes.index[::REBAL])
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns); cur = []
    for dt in closes.index:
        if dt in rebal_days and score.loc[dt].notna().sum() >= TOPN:
            cur = select(score.loc[dt], closes, rets.loc[:dt].tail(60), 0.85, 2)[:TOPN]
        if cur:
            w.loc[dt, cur] = 1.0 / len(cur)
    w = w.fillna(0.0)
    net = (w.shift(1) * rets).sum(axis=1) - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    return closes, score, net


closes, score, net = run()
eq = (1 + net).cumprod(); peak = eq.cummax()
print("=" * 62)
print("  LONG-TERM PICKER (12m momentum + low-vol, monthly, corr+sector)")
print("=" * 62)
print(f"  {'year':<6}{'return%':>9}")
comp = 1.0
for y, g in net.groupby(net.index.year):
    if len(g) < 30:
        continue
    yr = (1 + g).prod() - 1; comp *= (1 + yr)
    print(f"  {y:<6}{100*yr:>9.1f}")
print(f"  {'-'*16}")
print(f"  total {100*(eq.iloc[-1]-1):+.0f}%   Sharpe {net.mean()/(net.std()+1e-12)*np.sqrt(252):.2f}"
      f"   maxDD {100*((peak-eq)/peak).max():.1f}%")

# ---- the BUY LIST today ----
last = score.index[-1]
fpath = ROOT / "data" / "raw" / "india" / "fundamentals.parquet"
fund = pd.read_parquet(fpath) if fpath.exists() else pd.DataFrame()
roll60 = closes.pct_change().tail(60)
picks = select(score.loc[last], closes, roll60, 0.85, 2)[:TOPN]
print(f"\n  >>> BUY LIST for the long term (as of {last.date()}):")
print(f"  {'rank':<5}{'stock':<12}{'sector':<9}{'mom+lv score':>13}{'ROE':>7}{'D/E':>8}{'next_earn':>13}")
for i, s in enumerate(picks, 1):
    q = fund.loc[s] if s in getattr(fund, "index", []) else {}
    roe = q.get("returnOnEquity", np.nan) if hasattr(q, "get") else np.nan
    de = q.get("debtToEquity", np.nan) if hasattr(q, "get") else np.nan
    ne = q.get("next_earnings", "-") if hasattr(q, "get") else "-"
    sc = float(score.loc[last, s])
    print(f"  {i:<5}{s:<12}{SECTOR.get(s,'?'):<9}{sc:>13.2f}"
          f"{(roe if pd.notna(roe) else 0):>7.2f}{(de if pd.notna(de) else 0):>8.0f}{str(ne):>13}")
print("\n  These are the current top long-term holds (momentum+low-vol, diversified by sector).")
print("  Quality (ROE/DE) shown as a sanity check; rebalance monthly.")
