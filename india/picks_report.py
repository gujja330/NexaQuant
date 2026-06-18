# india/picks_report.py
"""
ONE clear report for the CHAMPION strategy — logic + year-by-year backtest + current picks
with prices and the exit rule. Removes the earlier confusion (the long_term variant's buy
list was shown by mistake; THIS is the validated champion).

CHAMPION = momentum(6m) + low-vol, top-5, WEEKLY rebalance, + VIX de-risk.
Backtest: +145% / ~6y, Sharpe 1.23, maxDD 13.8%, 6/7 profitable years.

Run: python india/picks_report.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import load, composite_score
from india.picker_pro import backtest, SECTOR

WEIGHTS = {"momentum": 0.6, "low_vol": 0.4}

print("=" * 74)
print("  NexaQuant India — CHAMPION strategy report")
print("=" * 74)
print("""
  LOGIC (how a stock gets picked):
    1. For every stock, each week compute two things, ranked ACROSS the universe (z-score):
         MOMENTUM  = its return over the last ~6 months (skip last 2 wks)  -> reward strength
         LOW-VOL   = inverse of its recent volatility                      -> reward steadiness
       composite score = 0.6*momentum_z + 0.4*lowvol_z
    2. Hold the TOP 5 scores, equal weight (20% each).
    3. VIX DE-RISK: when India VIX is in its high (fear) regime, cut exposure (defends crashes).
    4. EXIT RULE: re-rank WEEKLY -> a name is SOLD when it drops out of the top 5 (rotation).
       There is no fixed target price; it's a systematic rotation, not a one-shot trade.
""")

# ---- year-by-year backtest of the champion (VIX de-risk on) ----
net = backtest(vix_derisk=True)
eq = (1 + net).cumprod(); peak = eq.cummax()
print("  YEAR-BY-YEAR BACKTEST (Rs1,00,000 start, net of cost):")
print(f"  {'year':<6}{'start_Rs':>12}{'return%':>9}{'gain/loss_Rs':>14}{'end_Rs':>13}")
comp = 100000.0; yrows = []
for y, g in net.groupby(net.index.year):
    if len(g) < 30:
        continue
    yr = (1 + g).prod() - 1; start = comp; comp *= (1 + yr); gl = comp - start
    print(f"  {y:<6}{start:>12,.0f}{100*yr:>9.1f}{gl:>+14,.0f}{comp:>13,.0f}")
    yrows.append({"year": y, "start_rs": round(start), "return_pct": round(100*yr, 1),
                  "gain_loss_rs": round(gl), "end_rs": round(comp)})
OUTD = ROOT / "output"; OUTD.mkdir(exist_ok=True)
pd.DataFrame(yrows).to_csv(OUTD / "india_champion_yearly.csv", index=False)
print(f"  {'-'*28}")
print(f"  saved -> output/india_champion_yearly.csv  (net profit Rs{comp-100000:,.0f})")
print(f"  TOTAL {100*(eq.iloc[-1]-1):+.0f}%   Sharpe {net.mean()/(net.std()+1e-12)*np.sqrt(252):.2f}"
      f"   maxDD {100*((peak-eq)/peak).max():.1f}%   (Rs1,00,000 -> Rs{(1+net).cumprod().iloc[-1]*100000:,.0f})")

# ---- current picks WITH the numbers behind them ----
closes, _ = load()
score = composite_score(closes, WEIGHTS)
last = score.index[-1]
top = score.loc[last].dropna().sort_values(ascending=False).head(5)
print(f"\n  CURRENT TOP-5 (as of {last.date()}) — the metrics behind each pick:")
print(f"  {'rank':<5}{'stock':<12}{'sector':<8}{'price_Rs':>10}{'6m_ret%':>9}{'12m_ret%':>9}{'ann_vol%':>9}{'score':>7}")
for i, (s, sc) in enumerate(top.items(), 1):
    px = closes[s].iloc[-1]
    r6 = 100 * (closes[s].iloc[-1] / closes[s].iloc[-126] - 1) if len(closes) > 126 else np.nan
    r12 = 100 * (closes[s].iloc[-1] / closes[s].iloc[-252] - 1) if len(closes) > 252 else np.nan
    vol = 100 * closes[s].pct_change().tail(60).std() * np.sqrt(252)
    print(f"  {i:<5}{s:<12}{SECTOR.get(s,'?'):<8}{px:>10,.1f}{r6:>9.1f}{r12:>9.1f}{vol:>9.1f}{sc:>7.2f}")
print(f"""
  HOW TO READ IT:
    - price_Rs  = approx entry price (buy near this; ~20% of capital each).
    - 6m/12m_ret = why it's picked: strong past return (momentum).
    - ann_vol   = lower is better (the low-vol factor); steadier names preferred.
    - EXIT      = sell when it drops out of the weekly top-5 (no fixed target/stop).
  P(WIN) STATUS: NOT included here. The AI meta-label scored AUC 0.55 (borderline) on the
    weak per-stock trades; it is NOT wired into this picker. It can be added as an optional
    filter, but honestly its edge is marginal — the factor logic above is what drives returns.
""")
