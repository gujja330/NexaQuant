# research/sizing_overlay_test.py
"""
PHASE 1 sizing-overlay A/B (per-year walk-forward, BTC + gold H4, Option B sizing).

Compares, apples-to-apples, the confidence sizing engine with each optional overlay:
  base          : ADX confidence x lengthy-candle boost (current champion)
  +vol_target   : symmetric vol scaling (Phase 1a — expected to lose, sizes up in calm)
  +crash_protect: asymmetric de-risk, only cuts size in vol spikes (Phase 1b, risk-managed momentum)

Everything DYNAMIC: pairs + all risk numbers read from config (no hardcoding).
Keep an overlay only if it raises Sharpe / cuts drawdown without killing return.

Run: python research/sizing_overlay_test.py
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

PAIRS = [(s, "H4") for s in cfg().get("system", {}).get("symbols", ["BTCUSDm"])]
for extra in (("BTCUSDm", "H4"), ("XAUUSDm", "H4")):     # ensure both primaries present
    if extra not in PAIRS and (ROOT / f"data/raw/{extra[0]}_{extra[1]}.parquet").exists():
        PAIRS.append(extra)


def option_b_risk(conf):
    """Live-bot sizing: base% x confidence, capped at the top configured risk tier."""
    acct = cfg().get("account", {})
    base = float(acct.get("risk_per_trade", cfg().get("system", {}).get("risk_per_trade", 0.005)))
    tiers = cfg().get("sizing", {}).get("risk_tiers", [[99.0, 0.02]])
    cap = float(max(t[1] for t in tiers))
    return np.minimum(base * np.asarray(conf, float), cap)


def trades(df, sp, a, reg):
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    return pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")


def yearly(df, tr, **overlay):
    conf = playbook.confidence_size(df, **overlay).reindex(tr["entry_time"]).fillna(1.0).values
    rr = option_b_risk(conf)
    yrs = pd.to_datetime(tr["entry_time"]).dt.year
    out = []
    for y in sorted(yrs.unique()):
        m = (yrs == y).values
        if m.sum() < 10:
            continue
        rets = rr[m] * tr["R"].values[m]
        eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
        out.append((100 * (eq[-1] - 1), 100 * np.max((peak - eq) / peak),
                    rets.mean() / (rets.std() + 1e-9) * np.sqrt(len(rets))))
    arr = np.array(out) if out else None
    if arr is None:
        return None
    return {"pos": int((arr[:, 0] > 0).sum()), "n": len(arr), "avg": arr[:, 0].mean(),
            "worst": arr[:, 0].min(), "dd": arr[:, 1].max(), "sharpe": arr[:, 2].mean()}


VARIANTS = [("base", {}), ("+vol_target", {"vol_target": True}),
            ("+crash_protect", {"crash_protect": True})]
print("PHASE 1 — sizing-overlay A/B (per-year, Option B sizing)")
print(f"  {'pair':<9}{'variant':<16}{'pos yrs':>8}{'avg%/yr':>9}{'worst%':>8}{'maxDD%':>8}{'Sharpe':>8}")
for sym, tf in PAIRS:
    df = pd.read_parquet(ROOT / f"data/raw/{sym}_{tf}.parquet").sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14)
    reg = playbook.regime_labels(df, "adx"); tr = trades(df, sp, a, reg)
    for label, ov in VARIANTS:
        r = yearly(df, tr, **ov)
        if r:
            print(f"  {sym:<9}{label:<16}{r['pos']:>3}/{r['n']:<4}{r['avg']:>9.1f}"
                  f"{r['worst']:>8.1f}{r['dd']:>8.1f}{r['sharpe']:>8.2f}")
    print()
