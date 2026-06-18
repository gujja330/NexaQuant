# research/breakout_test.py
"""
Validate the VOLATILITY-BREAKOUT (Donchian) edge per-year on the trend instruments, and
measure its correlation with the trend sleeve. Config-driven (edges.breakout). A second edge
is only worth adding if it (a) stands on its own and (b) is meaningfully uncorrelated.

Run: python research/breakout_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import cfg, symbol_params
from strategy import playbook, breakout
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

RAW = ROOT / "data" / "raw"


def option_b_risk(conf):
    base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
    cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
    return np.minimum(base * np.asarray(conf, float), cap)


def edge_trades(df, sp, a, reg, kind, length):
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        if kind == "trend":
            ent = playbook.entries(df, side=side, regime=reg)
        else:
            ent = breakout.entries(df, side=side, n=length)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    return pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")


def daily_pnl(df, tr):
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    rr = option_b_risk(conf)
    r = pd.Series(rr * tr["R"].values, index=pd.to_datetime(tr["entry_time"]))
    return r.groupby(r.index.date).sum()


bc = cfg()["edges"]["breakout"]; tf = bc["timeframe"]; length = bc["length"]
print(f"VOLATILITY BREAKOUT (Donchian {length}) — {bc['instruments']} {tf}, Option B sizing\n")
for sym in bc["instruments"]:
    p = RAW / f"{sym}_{tf}.parquet"
    if not p.exists():
        print(f"  {sym}: no data"); continue
    df = pd.read_parquet(p).sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    bo = edge_trades(df, sp, a, reg, "breakout", length)
    tr = edge_trades(df, sp, a, reg, "trend", length)
    print(f"  {sym} {tf}: breakout {len(bo)} trades, win {100*(bo['R']>0).mean():.0f}%")
    yrs = pd.to_datetime(bo["entry_time"]).dt.year
    for y in sorted(yrs.unique()):
        m = (yrs == y).values
        if m.sum() < 8:
            continue
        rr = option_b_risk(playbook.confidence_size(df).reindex(bo["entry_time"]).fillna(1.0).values)[m]
        rets = rr * bo["R"].values[m]; eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
        print(f"      {y}  ret {100*(eq[-1]-1):+6.1f}%  maxDD {100*np.max((peak-eq)/peak):4.1f}%  "
              f"Sharpe {rets.mean()/(rets.std()+1e-12)*np.sqrt(len(rets)):5.2f}")
    bo_d, tr_d = daily_pnl(df, bo), daily_pnl(df, tr)
    j = pd.concat([bo_d.rename("bo"), tr_d.rename("tr")], axis=1).fillna(0.0)
    print(f"      corr breakout vs trend: {j['bo'].corr(j['tr']):+.2f}\n")
