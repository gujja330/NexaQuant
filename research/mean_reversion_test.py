# research/mean_reversion_test.py
"""
PHASE 4 — does a RANGE-REGIME mean-reversion sleeve add to the portfolio?

The trend playbook is idle in range regimes. This tests whether harvesting those ranges
(buy deep-discount/oversold, sell deep-premium/overbought, ONLY when regime='range') adds
return/Sharpe when combined with the trend edge — without fighting real trends.

Per-year, BTC + gold H4, Option B sizing, net of cost. Shows the sleeve STANDALONE and the
COMBINED book (trend + mean-reversion). Keep only if combined beats trend-only.

Run: python research/mean_reversion_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, cfg
from strategy import playbook, mean_reversion as mr
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

PAIRS = [("BTCUSDm", "H4"), ("XAUUSDm", "H4")]
PAIRS = [p for p in PAIRS if (ROOT / f"data/raw/{p[0]}_{p[1]}.parquet").exists()]


def option_b_risk(conf):
    base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
    cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
    return np.minimum(base * np.asarray(conf, float), cap)


def trend_trades(df, sp, a, reg, tsm, mg):
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg, tsm_confirm=tsm, macro_gate=mg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    return pd.concat([p for p in parts if not p.empty]) if parts else pd.DataFrame()


def mr_trades(df, sp, a, reg):
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = mr.entries(df, side=side, regime=reg)
        parts.append(simulate_trades(df, ent, a, sp["cost"], pip_size=sp["pip_size"],
                                     side=s, **mr.EXIT))
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts) if parts else pd.DataFrame()


def perf(df, tr):
    if tr is None or tr.empty:
        return None
    tr = tr.sort_values("entry_time")
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    rr = option_b_risk(conf); yrs = pd.to_datetime(tr["entry_time"]).dt.year
    rows = []
    for y in sorted(yrs.unique()):
        m = (yrs == y).values
        if m.sum() < 5:
            continue
        rets = rr[m] * tr["R"].values[m]
        eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
        rows.append((100 * (eq[-1] - 1), 100 * np.max((peak - eq) / peak),
                     rets.mean() / (rets.std() + 1e-9) * np.sqrt(len(rets))))
    if not rows:
        return None
    arr = np.array(rows)
    return {"trades": len(tr), "win": 100 * (tr["R"] > 0).mean(), "pos": int((arr[:, 0] > 0).sum()),
            "n": len(arr), "avg": arr[:, 0].mean(), "dd": arr[:, 1].max(), "sharpe": arr[:, 2].mean()}


print("PHASE 4 — range-regime mean-reversion sleeve (per-year, Option B)")
print(f"  {'pair':<9}{'book':<22}{'trades':>7}{'win%':>6}{'pos yrs':>8}{'avg%/yr':>9}{'maxDD%':>8}{'Sharpe':>8}")
for sym, tf in PAIRS:
    df = pd.read_parquet(ROOT / f"data/raw/{sym}_{tf}.parquet").sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    inst = cfg().get("instruments", {}).get(sym, {})
    tsm = float(inst.get("tsm_confirm", 0.0)); mg = bool(inst.get("macro_gate", False))
    trend = trend_trades(df, sp, a, reg, tsm, mg)
    mrev = mr_trades(df, sp, a, reg)
    combined = pd.concat([trend, mrev]) if not mrev.empty else trend
    for label, tr in (("trend only (champion)", trend), ("mean-reversion only", mrev),
                      ("trend + mean-reversion", combined)):
        r = perf(df, tr)
        if r:
            print(f"  {sym:<9}{label:<22}{r['trades']:>7}{r['win']:>5.0f}%{r['pos']:>4}/{r['n']:<3}"
                  f"{r['avg']:>9.1f}{r['dd']:>8.1f}{r['sharpe']:>8.2f}")
    print()
