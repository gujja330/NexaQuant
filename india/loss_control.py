# india/loss_control.py
"""
LOSS-CONTROL test on the champion picker (momentum+low-vol, top-5 weekly, VIX de-risk).
Goal: cut the SIZE of losses + the crash drawdown WITHOUT killing the +145% (cutting losses
usually trims winners too — net effect decides). Each lever tested alone + combined.

Levers:
  * trend_confirm : only buy names ABOVE their 200-DMA (skip already-rolling-over momentum)
  * mombreak      : exit a holding MID-WEEK if it closes below its 20-DMA (don't wait for rebal)
  * trail X%      : trailing stop — exit if it falls X% from its high since entry (a slot -> cash)
  * breadth       : when market breadth (% of universe > 200-DMA) collapses (<0.4), halve exposure
  * VIX de-risk   : champion baseline (half size when India VIX is in its high regime)

Reports total / Sharpe / maxDD / 2026 (the crash year) so we see loss-control vs return cost.
Run: python india/loss_control.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import load, composite_score, COST_BPS
from india.picker_pro import vix_regime

WEIGHTS = {"momentum": 0.6, "low_vol": 0.4}
TOPN, REBAL = 5, 5

closes, _ = load()
rets = closes.pct_change().fillna(0.0)
score = composite_score(closes, WEIGHTS)
ma200 = closes.rolling(200).mean()
ma20 = closes.rolling(20).mean()
breadth = (closes > ma200).mean(axis=1)               # fraction of universe in uptrend
vix_hi = vix_regime()
syms = list(closes.columns); col = {s: i for i, s in enumerate(syms)}
C, M200, M20, SC, R = closes.values, ma200.values, ma20.values, score.values, rets.values
dates = closes.index
rebal = set(range(0, len(dates), REBAL))


def run(trend_confirm=False, mombreak=False, trail=0.0, breadth_derisk=False, vix=True):
    w = np.zeros((len(dates), len(syms)))
    slots = []   # list of dicts: {c: col_idx, high: px, active: bool}
    for t in range(len(dates)):
        if t in rebal:
            order = np.argsort(-SC[t])
            picks = []
            for ci in order:
                if np.isnan(SC[t, ci]):
                    continue
                if trend_confirm and not (C[t, ci] > M200[t, ci]):
                    continue
                picks.append(ci)
                if len(picks) >= TOPN:
                    break
            slots = [{"c": ci, "high": C[t, ci], "active": True} for ci in picks]
        for s in slots:
            px = C[t, s["c"]]
            s["high"] = max(s["high"], px)
            if s["active"]:
                if trail and px < s["high"] * (1 - trail):
                    s["active"] = False
                if mombreak and not np.isnan(M20[t, s["c"]]) and px < M20[t, s["c"]]:
                    s["active"] = False
        for s in slots:
            if s["active"]:
                w[t, s["c"]] = 1.0 / TOPN
    W = pd.DataFrame(w, index=dates, columns=syms)
    net = (W.shift(1) * rets).sum(axis=1) - (W - W.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    if vix and vix_hi is not None:
        net = net * vix_hi.reindex(net.index).fillna(False).map({True: 0.5, False: 1.0})
    if breadth_derisk:
        net = net * (breadth.shift(1) < 0.4).reindex(net.index).fillna(False).map({True: 0.5, False: 1.0})
    return net


def stats(name, net):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    yr = {y: 100 * ((1 + g).prod() - 1) for y, g in net.groupby(net.index.year) if len(g) > 30}
    pos = sum(1 for v in yr.values() if v > 0)
    sh = net.mean() / (net.std() + 1e-12) * np.sqrt(252)
    print(f"  {name:<30}{100*(eq.iloc[-1]-1):>7.0f}%{sh:>7.2f}{100*((peak-eq)/peak).max():>8.1f}%"
          f"{yr.get(2026,0):>9.1f}{min(yr.values()):>8.1f}{pos:>4}/{len(yr)}")


print("=" * 86)
print("  LOSS-CONTROL test on champion (momentum+low-vol, top-5 weekly, VIX de-risk)")
print("=" * 86)
print(f"  {'variant':<30}{'total':>8}{'Sharpe':>7}{'maxDD':>8}{'2026%':>9}{'worst%':>8}{'posYr':>7}")
stats("champion (baseline)", run())
stats("+ trend-confirm entry", run(trend_confirm=True))
stats("+ momentum-break exit", run(mombreak=True))
stats("+ trailing stop 8%", run(trail=0.08))
stats("+ trailing stop 12%", run(trail=0.12))
stats("+ breadth de-risk", run(breadth_derisk=True))
stats("+ ALL (trend+break+trail12+breadth)", run(trend_confirm=True, mombreak=True, trail=0.12, breadth_derisk=True))
print("\n  Goal: lift 2026 (the crash) + cut maxDD WITHOUT crushing total/Sharpe. Keep only net wins.")
