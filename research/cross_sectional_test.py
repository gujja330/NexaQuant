# research/cross_sectional_test.py
"""
Validate the CROSS-SECTIONAL MOMENTUM edge (config-driven) and check it is UNCORRELATED
with the trend sleeve — the property that makes it worth adding to the portfolio.

All inputs from config (edges.xsec_momentum): universe, timeframe, lookback, skip, rebal,
cost. No hardcoding. Reports per-year return/Sharpe/maxDD + correlation to BTC trend P&L.

Run: python research/cross_sectional_test.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import cfg, symbol_params
from strategy.cross_sectional import backtest_xsec
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

RAW = ROOT / "data" / "raw"


def load_universe(symbols, tf):
    cols = {}
    for s in symbols:
        p = RAW / f"{s}_{tf}.parquet"
        if p.exists():
            cols[s] = pd.read_parquet(p)["close"].sort_index()
    closes = pd.DataFrame(cols).dropna(how="all")
    return closes.dropna()                                   # common-date aligned panel


def yearly(rets):
    out = []
    for y, g in rets.groupby(rets.index.year):
        if len(g) < 20:
            continue
        eq = (1 + g).cumprod(); peak = eq.cummax()
        out.append((y, 100 * (eq.iloc[-1] - 1), 100 * ((peak - eq) / peak).max(),
                    g.mean() / (g.std() + 1e-12) * np.sqrt(252)))
    return out


def trend_daily_returns(sym, tf):
    """Daily P&L series of the trend sleeve on one symbol (for correlation check)."""
    df = pd.read_parquet(RAW / f"{sym}_{tf}.parquet").sort_index()
    sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
    parts = []
    for side, s in (("long", 1), ("short", -1)):
        ent = playbook.entries(df, side=side, regime=reg)
        ex = playbook.momentum_exit_signal(df, side=side)
        parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=s, **playbook.EXIT))
    tr = pd.concat([p for p in parts if not p.empty])
    base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
    r = pd.Series(0.0, index=df.index)
    for _, t in tr.iterrows():
        r[pd.to_datetime(t["entry_time"])] += base * t["R"]      # book the R at entry day
    return r.groupby(r.index.date).sum()


ec = cfg()["edges"]["xsec_momentum"]
closes = load_universe(ec["universe"], ec["timeframe"])
print(f"CROSS-SECTIONAL MOMENTUM — {ec['universe']} {ec['timeframe']} "
      f"(lookback {ec['lookback']}, skip {ec['skip']}, rebal {ec['rebal']}, cost {ec['cost_bps']}bps)")
print(f"  panel: {closes.shape[0]} aligned bars, {closes.index[0].date()} -> {closes.index[-1].date()}\n")

for lo in ("L/S", "long-only"):
    rets = backtest_xsec(closes, ec["lookback"], ec["skip"], ec["rebal"], ec["cost_bps"],
                         long_only=(lo == "long-only"))
    eq = (1 + rets).cumprod()
    print(f"  [{lo}]  total {100*(eq.iloc[-1]-1):+.1f}%   "
          f"Sharpe {rets.mean()/(rets.std()+1e-12)*np.sqrt(252):.2f}   "
          f"maxDD {100*((eq.cummax()-eq)/eq.cummax()).max():.1f}%")
    for y, ret, dd, sh in yearly(rets):
        print(f"      {y}  ret {ret:+6.1f}%  maxDD {dd:4.1f}%  Sharpe {sh:5.2f}")
    print()

# correlation with the trend sleeve (lower = better diversifier)
xs = backtest_xsec(closes, ec["lookback"], ec["skip"], ec["rebal"], ec["cost_bps"]); xs.index = xs.index.date
tr = trend_daily_returns("BTCUSDm", "H4")
j = pd.concat([xs.rename("xsec"), tr.rename("trend")], axis=1).fillna(0.0)
corr = j["xsec"].corr(j["trend"])
print(f"  correlation xsec vs BTC-trend daily P&L: {corr:+.2f}   "
      f"({'GOOD diversifier' if abs(corr) < 0.3 else 'somewhat correlated'})")
