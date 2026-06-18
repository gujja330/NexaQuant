# india/intraday_engine.py
"""
INTRADAY engine on HOURLY NSE bars — the "analyst day-trade" rules, made systematic + tested.
Honest evidence-first: most intraday tips are unvalidated and our fast-TF crypto tests LOST,
so the prior is low — we let the data decide, net of intraday costs, with HARD stops.

Rules per stock per day (one trade/day max):
  * OPENING RANGE = first hourly bar (9:15-10:15) high/low.
  * ENTRY (ORB + VWAP confluence): a later bar closes ABOVE the OR-high AND above intraday VWAP
    -> LONG; closes BELOW OR-low AND below VWAP -> SHORT. (optional volume-surge filter)
  * HARD STOP = the opposite end of the opening range (mandatory).
  * EXIT = stop hit intrabar, else EOD square-off (last bar) — never carry overnight.

Run: python india/intraday_engine.py
"""
import sys, glob, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
INTRA = ROOT / "data" / "raw" / "india" / "intraday"
COST_BPS = 10.0                       # intraday round-trip (cheaper STT than delivery) + slippage
VOL_SURGE = 1.0                       # require bar volume >= this x day's avg-so-far (1.0 = off-ish)


def day_trade(g):
    """One day's bars (sorted). Returns (ret_pct, side, reason) for at most one trade, or None."""
    if len(g) < 3:
        return None
    o = g["open"].values; h = g["high"].values; l = g["low"].values
    c = g["close"].values; v = g["volume"].values
    or_hi, or_lo = h[0], l[0]
    tp = (h + l + c) / 3.0
    cum_pv = np.cumsum(tp * v); cum_v = np.cumsum(v)
    vwap = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-9), c)
    for i in range(1, len(g)):
        volok = v[i] >= VOL_SURGE * (cum_v[i] / (i + 1))
        if c[i] > or_hi and c[i] > vwap[i] and volok:
            entry, stop, sd = c[i], or_lo, 1
        elif c[i] < or_lo and c[i] < vwap[i] and volok:
            entry, stop, sd = c[i], or_hi, -1
        else:
            continue
        # manage to EOD with the hard stop
        for j in range(i + 1, len(g)):
            if sd == 1 and l[j] <= stop:
                return (100 * (stop / entry - 1), sd, "stop")
            if sd == -1 and h[j] >= stop:
                return (100 * (entry / stop - 1) * -1 if False else 100 * (entry - stop) / entry, sd, "stop")
        exitpx = c[-1]
        ret = 100 * (exitpx - entry) / entry * sd
        return (ret, sd, "eod")
    return None


def backtest():
    rows = []
    for f in sorted(glob.glob(str(INTRA / "*_H1.parquet"))):
        sym = os.path.basename(f).replace("_H1.parquet", "")
        if sym == "NSEI":
            continue
        df = pd.read_parquet(f).sort_index()
        df["date"] = pd.to_datetime(df.index).date
        for d, g in df.groupby("date"):
            r = day_trade(g.sort_index())
            if r is None:
                continue
            ret = r[0] - COST_BPS / 100.0     # net of cost (bps -> %)
            rows.append({"stock": sym, "date": d, "year": pd.Timestamp(d).year,
                         "side": "long" if r[1] == 1 else "short", "ret_pct": round(ret, 3),
                         "reason": r[2], "win": ret > 0})
    return pd.DataFrame(rows)


bt = backtest()
OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)
bt.to_csv(OUT / "india_intraday_trades.csv", index=False)
print("=" * 70)
print(f"  INTRADAY (ORB+VWAP, hourly, hard stop+EOD) — {len(bt)} trades, net {COST_BPS:.0f}bps")
print("=" * 70)
print(f"  {'year':<6}{'trades':>7}{'WINS':>6}{'LOSSES':>8}{'win%':>6}{'avg_ret%':>9}{'total%':>9}")
for y, d in bt.groupby("year"):
    w = int(d["win"].sum()); l = int((~d["win"]).sum())
    print(f"  {y:<6}{len(d):>7}{w:>6}{l:>8}{100*d['win'].mean():>5.0f}%{d['ret_pct'].mean():>9.3f}{d['ret_pct'].sum():>9.1f}")
print(f"  {'-'*52}")
print(f"  {'ALL':<6}{len(bt):>7}{int(bt['win'].sum()):>6}{int((~bt['win']).sum()):>8}"
      f"{100*bt['win'].mean():>5.0f}%{bt['ret_pct'].mean():>9.3f}{bt['ret_pct'].sum():>9.1f}")
print(f"\n  per-trade expectancy: {bt['ret_pct'].mean():.3f}% (net). Positive = edge, ~0/neg = no edge.")
print(f"  full trades -> output/india_intraday_trades.csv")
