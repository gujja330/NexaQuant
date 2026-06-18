# india/validate_india.py
"""
Validate the edge on INDIAN equities (parallel to the gold/BTC validators). Tests, net of
realistic Indian costs, on the pulled NSE universe:

  1. CROSS-SECTIONAL MOMENTUM — rank the universe by trailing return, long top-N, rebalance.
     (The "pick the right stocks" model — needs breadth, which NSE large-caps provide.)
  2. TREND + BREAKOUT per instrument — does our existing engine work on indices/stocks?

Honest: daily data, liquid large-caps only (survivorship-light), costs modelled. Evidence
first — we only pursue the broker adapter if an edge actually shows here.

Run:  python india/validate_india.py
"""
import sys, glob, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy import playbook, breakout
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

RAW = ROOT / "data" / "raw" / "india"
COST_BPS = 16.0 + 5.0            # India round-trip ~ brokerage+STT+GST+SEBI (~0.16%) + slippage (~0.05%)
INDICES = {"NSEI", "NSEBANK"}


def load():
    out = {}
    for f in sorted(glob.glob(str(RAW / "*_D1.parquet"))):
        s = os.path.basename(f).replace("_D1.parquet", "")
        out[s] = pd.read_parquet(f).sort_index()
    return out


def per_year(rets):
    rows = []
    for y, g in rets.groupby(rets.index.year):
        if len(g) < 30:
            continue
        eq = (1 + g).cumprod(); peak = eq.cummax()
        rows.append((y, 100 * (eq.iloc[-1] - 1), 100 * ((peak - eq) / peak).max(),
                     g.mean() / (g.std() + 1e-12) * np.sqrt(252)))
    return rows


# ---------------- 1. cross-sectional momentum ----------------
def cross_sectional(data, lookback=120, skip=10, topn=5, rebal=5):
    stocks = [s for s in data if s not in INDICES]
    closes = pd.DataFrame({s: data[s]["close"] for s in stocks}).dropna()
    rets = closes.pct_change().fillna(0.0)
    mom = closes.shift(skip) / closes.shift(lookback) - 1.0
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for dt, row in mom.iterrows():
        r = row.dropna()
        if len(r) < topn:
            continue
        winners = r.sort_values(ascending=False).index[:topn]
        w.loc[dt, winners] = 1.0 / topn
    mask = np.zeros(len(closes), dtype=bool); mask[::rebal] = True
    w[~mask] = np.nan; w = w.ffill().fillna(0.0)
    gross = (w.shift(1) * rets).sum(axis=1)
    turnover = (w - w.shift(1)).abs().sum(axis=1)
    net = gross - turnover * (COST_BPS / 1e4)
    return net.rename("xsec")


# ---------------- 2. trend + breakout per instrument ----------------
def edge_per_instrument(data):
    print(f"\n  {'symbol':<12}{'edge':<9}{'trades':>7}{'win%':>6}{'totalR':>9}{'Sharpe':>8}")
    keep = []
    for s, df in data.items():
        from config_loader import symbol_params
        sp = symbol_params(s, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
        for kind in ("trend", "breakout"):
            parts = []
            for side, sd in (("long", 1), ("short", -1)):
                ent = playbook.entries(df, side=side, regime=reg) if kind == "trend" \
                      else breakout.entries(df, side=side, n=20)
                ex = playbook.momentum_exit_signal(df, side=side)
                parts.append(simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                             pip_size=sp["pip_size"], side=sd, **playbook.EXIT))
            tr = pd.concat([p for p in parts if not p.empty]) if parts else pd.DataFrame()
            if tr.empty or len(tr) < 20:
                continue
            r = pd.Series((0.005 * tr["R"]).values, index=pd.to_datetime(tr["entry_time"])).groupby(level=0).sum()
            sh = r.mean() / (r.std() + 1e-12) * np.sqrt(252)
            tot = tr["R"].sum()
            if sh > 0.4:
                keep.append(f"{kind}:{s}")
            print(f"  {s:<12}{kind:<9}{len(tr):>7}{100*(tr['R']>0).mean():>5.0f}%{tot:>9.1f}{sh:>8.2f}")
    return keep


data = load()
print("=" * 78)
print(f"  NexaQuant INDIA — validation on {len(data)} NSE symbols (daily, net ~{COST_BPS:.0f}bps)")
print("=" * 78)

print("\n  [1] CROSS-SECTIONAL MOMENTUM (rank universe, long top-5, weekly rebalance)")
xs = cross_sectional(data)
eq = (1 + xs).cumprod(); peak = eq.cummax()
print(f"      {'year':<6}{'return%':>9}{'maxDD%':>8}{'Sharpe':>8}")
pos = 0; rows = per_year(xs)
for y, r, d, s in rows:
    pos += r > 0
    print(f"      {y:<6}{r:>9.1f}{d:>7.1f}%{s:>8.2f}")
print(f"      {'-'*30}")
print(f"      FULL: {100*(eq.iloc[-1]-1):+.0f}%  maxDD {100*((peak-eq)/peak).max():.1f}%  "
      f"Sharpe {xs.mean()/(xs.std()+1e-12)*np.sqrt(252):.2f}  | profitable yrs {pos}/{len(rows)}")

print("\n  [2] TREND + BREAKOUT per instrument (which names have edge)")
keep = edge_per_instrument(data)
print(f"\n  passed gate (standalone Sharpe>0.4): {len(keep)} -> {keep[:12]}{'...' if len(keep)>12 else ''}")
