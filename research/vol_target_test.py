# research/vol_target_test.py
"""
PHASE 1a — does an explicit VOLATILITY-TARGETING overlay beat our current sizing?

Our risk-%/ATR-stop sizing already targets volatility IMPLICITLY (wider ATR -> smaller
position for the same % risk). AQR/Alpha-Architect show explicit vol-scaling lifts Sharpe
~0.40 -> 0.48-0.51 on equities — but that's on top of FIXED-size exposure, not our already
risk-normalised book. So the honest test: confidence sizing WITH vs WITHOUT the overlay,
per-year walk-forward, BTC + gold H4. Keep it only if it raises Sharpe without worse DD.

Run: python research/vol_target_test.py
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

# DYNAMIC: pairs/timeframes from config, nothing hardcoded
PAIRS = [(s, "H4") for s in cfg().get("system", {}).get("symbols", ["BTCUSDm"])]
if not any(s == "BTCUSDm" for s, _ in PAIRS):
    PAIRS = [("BTCUSDm", "H4"), ("XAUUSDm", "H4")]


def option_b_risk(conf):
    """Option B sizing, exactly as the live bot does it (_calc_lots): risk a base % of equity
    scaled by the confidence multiplier, capped at the top risk tier. All values read from
    config (account.risk_per_trade, sizing.risk_tiers) — no hardcoded numbers."""
    acct = cfg().get("account", {})
    base = float(acct.get("risk_per_trade", cfg().get("system", {}).get("risk_per_trade", 0.005)))
    tiers = cfg().get("sizing", {}).get("risk_tiers", [[99.0, 0.02]])
    cap = float(max(t[1] for t in tiers))                 # max risk fraction allowed
    return np.minimum(base * np.asarray(conf, float), cap)


def trades(df, sp, a, reg):
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    return pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")


def yearly(df, tr, vol_target):
    conf = playbook.confidence_size(df, vol_target=vol_target).reindex(tr["entry_time"]).fillna(1.0).values
    rr = option_b_risk(conf)                              # Option B: base% x confidence, capped
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
    if not out:
        return None
    arr = np.array(out)
    return {"pos_yrs": int((arr[:, 0] > 0).sum()), "n": len(arr), "avg": arr[:, 0].mean(),
            "worst": arr[:, 0].min(), "maxdd": arr[:, 1].max(), "sharpe": arr[:, 2].mean()}


print("PHASE 1a — VOLATILITY-TARGETING overlay A/B (per-year, BTC + gold H4)")
print(f"  {'pair':<9}{'overlay':<9}{'pos yrs':>8}{'avg%/yr':>9}{'worst%':>8}{'maxDD%':>8}{'Sharpe':>8}")
for sym, tf in PAIRS:
    p = ROOT / f"data/raw/{sym}_{tf}.parquet"
    if not p.exists():
        print(f"  {sym} {tf}: no data"); continue
    df = pd.read_parquet(p).sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14)
    reg = playbook.regime_labels(df, "adx"); tr = trades(df, sp, a, reg)
    for label, vt in (("OFF", False), ("ON", True)):
        r = yearly(df, tr, vt)
        if r:
            print(f"  {sym:<9}{label:<9}{r['pos_yrs']:>3}/{r['n']:<4}{r['avg']:>9.1f}"
                  f"{r['worst']:>8.1f}{r['maxdd']:>8.1f}{r['sharpe']:>8.2f}")
    print()
