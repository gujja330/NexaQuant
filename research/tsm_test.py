# research/tsm_test.py
"""
PHASE 2a — does MULTI-LOOKBACK TSM confirmation improve entry quality?

Moskowitz/AQR: time-series momentum is a decades-stable edge. Our entry uses a single
EMA20/50 signal; requiring several momentum horizons (20/60/120/240 bars) to AGREE with the
trade direction should drop low-quality entries. Tested as an ENTRY FILTER at rising
agreement thresholds, per-year, BTC + gold H4, Option B sizing, net of cost.

Keep it only if a threshold lifts Sharpe / win% without gutting trade count or return.
Everything dynamic (pairs + lookbacks + risk from config).

Run: python research/tsm_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, cfg
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

PAIRS = [("BTCUSDm", "H4"), ("XAUUSDm", "H4")]
PAIRS = [p for p in PAIRS if (ROOT / f"data/raw/{p[0]}_{p[1]}.parquet").exists()]


def option_b_risk(conf):
    acct = cfg().get("account", {})
    base = float(acct.get("risk_per_trade", 0.005))
    cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
    return np.minimum(base * np.asarray(conf, float), cap)


def build(df, sp, a, reg, thr):
    """Entries filtered so that >= thr fraction of TSM lookbacks agree with the side."""
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg)
        if thr > 0:
            ent = ent & (playbook.tsm_score(df, side=side) >= thr)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    return pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")


def metrics(df, tr):
    if tr.empty:
        return None
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    rr = option_b_risk(conf); yrs = pd.to_datetime(tr["entry_time"]).dt.year
    out = []
    for y in sorted(yrs.unique()):
        m = (yrs == y).values
        if m.sum() < 8:
            continue
        rets = rr[m] * tr["R"].values[m]
        eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
        out.append((100 * (eq[-1] - 1), 100 * np.max((peak - eq) / peak),
                    rets.mean() / (rets.std() + 1e-9) * np.sqrt(len(rets))))
    if not out:
        return None
    arr = np.array(out)
    return {"trades": len(tr), "win": 100 * (tr["R"] > 0).mean(), "pos": int((arr[:, 0] > 0).sum()),
            "n": len(arr), "avg": arr[:, 0].mean(), "dd": arr[:, 1].max(), "sharpe": arr[:, 2].mean()}


print("PHASE 2a — multi-lookback TSM confirmation as entry filter (per-year, Option B)")
print(f"  lookbacks = {cfg().get('signals', {}).get('tsm_lookbacks', [20, 60, 120, 240])} bars")
print(f"  {'pair':<9}{'thr':<6}{'trades':>7}{'win%':>6}{'pos yrs':>8}{'avg%/yr':>9}{'maxDD%':>8}{'Sharpe':>8}")
for sym, tf in PAIRS:
    df = pd.read_parquet(ROOT / f"data/raw/{sym}_{tf}.parquet").sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    for thr in (0.0, 0.5, 0.75, 1.0):
        r = metrics(df, build(df, sp, a, reg, thr))
        if r:
            tag = "base" if thr == 0 else f">={thr:.2f}"
            print(f"  {sym:<9}{tag:<6}{r['trades']:>7}{r['win']:>5.0f}%{r['pos']:>4}/{r['n']:<3}"
                  f"{r['avg']:>9.1f}{r['dd']:>8.1f}{r['sharpe']:>8.2f}")
    print()
