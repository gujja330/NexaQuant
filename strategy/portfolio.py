# strategy/portfolio.py
"""
MULTI-EDGE PORTFOLIO ENGINE — the consistency layer.

Combines every validated (edge x instrument) sleeve into one book with EQUAL-RISK (inverse-
volatility) weighting, so no single edge or instrument dominates and a drawdown in one sleeve
is cushioned by the others. This is the mechanism that turns a regime-dependent strategy into
a consistent, long-term one (diversification = the only free lunch).

Fully config-driven (the `edges` block): add an edge or instrument there, not in code.
Each sleeve's P&L uses Option B sizing (base% x confidence), so it matches live behaviour.
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


def _option_b_risk(conf):
    base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
    cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
    return np.minimum(base * np.asarray(conf, float), cap)


def _sleeve_daily(sym, tf, kind, length=20):
    """Daily P&L series for one (edge, instrument) sleeve, Option B sizing, net of cost."""
    p = RAW / f"{sym}_{tf}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p).sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    inst = cfg().get("instruments", {}).get(sym, {})
    tsm = float(inst.get("tsm_confirm", 0.0)); mg = bool(inst.get("macro_gate", False))
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        if kind == "trend":
            ent = playbook.entries(df, side=side, regime=reg, tsm_confirm=tsm, macro_gate=mg)
        else:
            ent = breakout.entries(df, side=side, n=length)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    tr = pd.concat([q for q in parts if not q.empty]).sort_values("entry_time")
    if tr.empty:
        return None
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    r = pd.Series(_option_b_risk(conf) * tr["R"].values, index=pd.to_datetime(tr["entry_time"]))
    return r.groupby(r.index.normalize()).sum()


def sleeves_from_config():
    """Build all enabled (edge x instrument) sleeves declared in the `edges` config block."""
    edges = cfg().get("edges", {}); out = {}
    if edges.get("trend", {}).get("enabled"):
        e = edges["trend"]
        for s in e["instruments"]:
            d = _sleeve_daily(s, e["timeframe"], "trend")
            if d is not None:
                out[f"trend:{s}"] = d
    if edges.get("breakout", {}).get("enabled"):
        e = edges["breakout"]
        for s in e["instruments"]:
            d = _sleeve_daily(s, e["timeframe"], "breakout", e.get("length", 20))
            if d is not None:
                out[f"breakout:{s}"] = d
    return out


def combine_equal_risk(sleeves, vol_window=63):
    """Inverse-volatility (equal-risk) blend of sleeve daily P&L. Weights use a CAUSAL rolling
    vol (shifted) so there is no lookahead; sleeves with no recent activity get zero weight."""
    if not sleeves:
        return pd.Series(dtype=float)
    panel = pd.DataFrame(sleeves).sort_index().fillna(0.0)
    vol = panel.rolling(vol_window, min_periods=10).std().shift(1)
    inv = (1.0 / vol).replace([np.inf, -np.inf], np.nan)
    w = inv.div(inv.sum(axis=1), axis=0).fillna(0.0)                 # weights sum to 1 per day
    return (w * panel).sum(axis=1).rename("portfolio")


def per_year(rets):
    rows = []
    for y, g in rets.groupby(rets.index.year):
        if len(g) < 10:
            continue
        eq = (1 + g).cumprod(); peak = eq.cummax()
        rows.append((y, 100 * (eq.iloc[-1] - 1), 100 * ((peak - eq) / peak).max(),
                     g.mean() / (g.std() + 1e-12) * np.sqrt(252)))
    return rows
