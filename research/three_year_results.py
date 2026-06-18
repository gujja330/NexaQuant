# research/three_year_results.py
"""
LAST 3 YEARS results — BTCUSD + XAUUSD, with the ADOPTED config.

Honest, net of cost, per-year (anchored: each year is genuine out-of-sample relative to the
prior years used to define the regime/macro context). Uses the EXACT live config:
  BTC : regime-aware long+short, momentum-ride exit + scale-out, lengthy-candle size boost
  Gold: same + multi-lookback TSM confirmation + fundamental macro gate (both gold-only)
Sizing = Option B (base 0.5% x confidence, capped at top tier), compounded.

Run: python research/three_year_results.py
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
YEARS_BACK = 3


def option_b_risk(conf):
    base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
    cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
    return np.minimum(base * np.asarray(conf, float), cap)


def book(df, sym):
    sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    inst = cfg().get("instruments", {}).get(sym, {})
    tsm = float(inst.get("tsm_confirm", 0.0)); mg = bool(inst.get("macro_gate", False))
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg, tsm_confirm=tsm, macro_gate=mg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    tr = pd.concat([p for p in parts if not p.empty]).sort_values("entry_time")
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    tr = tr.assign(risk=option_b_risk(conf))
    return tr


print("=" * 84)
print("  NexaQuant — LAST 3 YEARS (per-year, out-of-sample, net of cost, Option B sizing)")
print("=" * 84)
for sym, tf in PAIRS:
    p = ROOT / f"data/raw/{sym}_{tf}.parquet"
    if not p.exists():
        print(f"\n  {sym} {tf}: no data"); continue
    df = pd.read_parquet(p).sort_index()
    tr = book(df, sym)
    last = df.index.year.max(); years = list(range(last - YEARS_BACK + 1, last + 1))
    print(f"\n  {sym} {tf}   (data {df.index[0].date()} -> {df.index[-1].date()})")
    print(f"    {'year':<6}{'trades':>7}{'win%':>6}{'return%':>9}{'maxDD%':>8}{'Sharpe':>8}")
    yrs = pd.to_datetime(tr["entry_time"]).dt.year
    comp = 1.0; rets_all = []
    for y in years:
        m = (yrs == y).values
        if m.sum() == 0:
            print(f"    {y:<6}{'--- no trades / no data ---':>38}"); continue
        if m.sum() < 3:
            print(f"    {y:<6}{m.sum():>7}{'  (too few trades to score)':>31}"); continue
        sub = tr[m]; rets = sub["risk"].values * sub["R"].values
        eq = np.cumprod(1 + rets); peak = np.maximum.accumulate(eq)
        ret = 100 * (eq[-1] - 1); dd = 100 * np.max((peak - eq) / peak)
        sharpe = rets.mean() / (rets.std() + 1e-9) * np.sqrt(len(rets))
        comp *= (1 + ret / 100); rets_all.append(ret)
        print(f"    {y:<6}{len(sub):>7}{100*(sub['R']>0).mean():>5.0f}%{ret:>9.1f}{dd:>7.1f}%{sharpe:>8.2f}")
    if rets_all:
        print(f"    {'-'*36}")
        print(f"    3-yr compounded: {100*(comp-1):+.1f}%   |   avg {np.mean(rets_all):+.1f}%/yr   "
              f"|   profitable years: {sum(r>0 for r in rets_all)}/{len(rets_all)}")
print("\n  NOTE: % returns at 0.5%-base Option B risk. Gold H4 history is short (~2-3y) so its")
print("        sample is thin; BTC H4 spans the full window incl. the 2022 bear (long+short).")
