# india/trade_blotter.py
"""
TRADE BLOTTER — every individual trade the bot would have taken on each NSE stock, with
entry/exit DATES, entry/exit PRICES, % profit, R-multiple, bars held, exit reason, win/loss.

Runs both edges (trend + breakout, long+short) per stock, net of cost. Writes a full CSV
(output/india_trades.csv — open in Excel) and prints a readable sample + per-stock summary.

Run: python india/trade_blotter.py
"""
import sys, glob, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params
from strategy import playbook, breakout
from strategy.smc import atr
from backtest.trade_sim import simulate_trades

RAW = ROOT / "data" / "raw" / "india"
OUTDIR = ROOT / "output"; OUTDIR.mkdir(exist_ok=True)
CAPITAL_PER_TRADE = 10000.0          # notional per trade for the ₹ P&L view


def all_trades():
    rows = []
    for f in sorted(glob.glob(str(RAW / "*_D1.parquet"))):
        sym = os.path.basename(f).replace("_D1.parquet", "")
        if sym == "fundamentals":
            continue
        df = pd.read_parquet(f).sort_index()
        sp = symbol_params(sym, df["close"]); a = atr(df, 14); reg = playbook.regime_labels(df, "adx")
        for edge in ("trend", "breakout"):
            for side, sd in (("long", 1), ("short", -1)):
                ent = playbook.entries(df, side=side, regime=reg) if edge == "trend" \
                      else breakout.entries(df, side=side, n=20)
                ex = playbook.momentum_exit_signal(df, side=side)
                tr = simulate_trades(df, ent, a, sp["cost"], exit_signal=ex,
                                     pip_size=sp["pip_size"], side=sd, **playbook.EXIT)
                if tr.empty:
                    continue
                tr = tr.copy()
                tr.insert(0, "stock", sym); tr.insert(1, "edge", edge)
                sgn = np.where(tr["side"] == "long", 1, -1)
                tr["px_diff"] = (tr["exit_px"] - tr["entry_px"]).round(2)        # raw entry->exit move
                tr["ret_pct"] = (sgn * (tr["exit_px"] - tr["entry_px"]) / tr["entry_px"] * 100).round(2)
                tr["pnl_rs"] = (tr["ret_pct"] / 100 * CAPITAL_PER_TRADE).round(0)
                tr["days_held"] = tr["bars"].astype(int)                         # daily bars = days
                rows.append(tr)
    out = pd.concat(rows, ignore_index=True)
    out["entry_date"] = pd.to_datetime(out["entry_time"]).dt.date
    out["exit_date"] = pd.to_datetime(out["exit_time"]).dt.date
    out["year"] = pd.to_datetime(out["entry_time"]).dt.year
    cols = ["stock", "edge", "side", "entry_date", "entry_px", "sl_px", "exit_date", "exit_px",
            "px_diff", "days_held", "ret_pct", "pnl_rs", "R", "reason", "win", "year"]
    return out[cols].sort_values(["stock", "entry_date"]).reset_index(drop=True)


bl = all_trades()
csv = OUTDIR / "india_trades.csv"
bl.to_csv(csv, index=False)
print(f"FULL BLOTTER -> {csv}   ({len(bl)} trades across {bl['stock'].nunique()} stocks)\n")

# readable sample: one stock's trades end-to-end
demo = "RELIANCE" if "RELIANCE" in bl["stock"].values else bl["stock"].iloc[0]
print(f"=== SAMPLE: every {demo} trade (entry->exit, price, % , Rs on Rs10k/trade) ===")
d = bl[bl["stock"] == demo]
print(d[["edge", "side", "entry_date", "entry_px", "exit_date", "exit_px", "ret_pct", "pnl_rs", "R", "reason"]]
      .to_string(index=False))

print("\n=== YEARLY SUMMARY (wins vs losses + net P&L, Rs10k/trade) ===")
print(f"  {'year':<6}{'trades':>7}{'WINS':>6}{'LOSSES':>8}{'win%':>6}{'avg_days':>9}{'net_Rs':>10}{'sumR':>8}")
yr = bl.groupby("year")
for y, d in yr:
    w = int(d["win"].sum()); l = int((~d["win"]).sum())
    print(f"  {y:<6}{len(d):>7}{w:>6}{l:>8}{100*d['win'].mean():>5.0f}%"
          f"{d['days_held'].mean():>9.1f}{d['pnl_rs'].sum():>10,.0f}{d['R'].sum():>8.1f}")
print(f"  {'-'*60}")
print(f"  {'ALL':<6}{len(bl):>7}{int(bl['win'].sum()):>6}{int((~bl['win']).sum()):>8}"
      f"{100*bl['win'].mean():>5.0f}%{bl['days_held'].mean():>9.1f}{bl['pnl_rs'].sum():>10,.0f}{bl['R'].sum():>8.1f}")

print("\n=== PER-STOCK SUMMARY (all trades, Rs10k/trade notional) ===")
g = bl.groupby("stock").agg(trades=("R", "size"), wins=("win", "sum"),
                            win_pct=("win", lambda s: round(100*s.mean())),
                            avg_days=("days_held", "mean"),
                            total_pnl_rs=("pnl_rs", "sum"), sum_R=("R", "sum")).round(1).sort_values("sum_R", ascending=False)
print(g.to_string())
print(f"\n  Columns now include: sl_px (stop), days_held, px_diff (entry->exit), win (True/False).")
print(f"  Open output/india_trades.csv in Excel for the full trade-by-trade list.")
