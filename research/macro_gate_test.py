# research/macro_gate_test.py
"""
PHASE 2b — does a FUNDAMENTAL (macro) bias gate add to gold, on top of the TSM filter?

Thesis (long held in this project): fundamentals + technicals together = stronger trades.
Test on gold H4: require macro bias (real yields + DXY falling = gold-bullish) to AGREE with
the trade side. Compared per-year vs the current gold champion (regime + TSM-confirm).

Honest limits: FUNDAMENTALS.parquet starts 2023-07, so this only covers the recent window;
treat as indicative, confirm later on deep daily gold. Everything config-driven.

Run: python research/macro_gate_test.py   (needs FUNDAMENTALS.parquet — run data/fundamentals.py first)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, cfg
from strategy import playbook
from strategy.fundamental_bias import macro_agrees
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

SYM, TF = "XAUUSDm", "H4"


def option_b_risk(conf):
    base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
    cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
    return np.minimum(base * np.asarray(conf, float), cap)


def run(df, sp, a, reg, tsm, macro):
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg, tsm_confirm=tsm)
        if macro:
            ent = ent & macro_agrees(df, side)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    tr = pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")
    if tr.empty:
        return None
    # restrict to the period where macro data exists for a fair comparison
    tr = tr[pd.to_datetime(tr["entry_time"]) >= pd.Timestamp("2023-07-20")]
    if tr.empty:
        return None
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    rr = option_b_risk(conf)
    rets = rr * tr["R"].values
    eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
    return {"trades": len(tr), "win": 100 * (tr["R"] > 0).mean(),
            "ret": 100 * (eq[-1] - 1), "dd": 100 * np.max((peak - eq) / peak),
            "sharpe": rets.mean() / (rets.std() + 1e-9) * np.sqrt(len(rets))}


df = pd.read_parquet(ROOT / f"data/raw/{SYM}_{TF}.parquet").sort_index()
sp = symbol_params(SYM, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
tsm_cfg = float(cfg().get("instruments", {}).get(SYM, {}).get("tsm_confirm", 0.0))

print(f"PHASE 2b — fundamental macro gate on {SYM} {TF} (since 2023-07, Option B sizing)")
print(f"  {'variant':<26}{'trades':>7}{'win%':>6}{'ret%':>8}{'maxDD%':>8}{'Sharpe':>8}")
for label, tsm, macro in (("regime only", 0.0, False),
                          ("regime + TSM (champion)", tsm_cfg, False),
                          ("regime + TSM + macro", tsm_cfg, True),
                          ("regime + macro only", 0.0, True)):
    r = run(df, sp, a, reg, tsm, macro)
    if r:
        print(f"  {label:<26}{r['trades']:>7}{r['win']:>5.0f}%{r['ret']:>8.1f}{r['dd']:>7.1f}%{r['sharpe']:>8.2f}")
