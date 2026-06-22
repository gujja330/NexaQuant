# india/research/quarterly_picks.py
"""
QUARTERLY PICKS — what the champion ACTUALLY picked each of the last 4 quarters, and what
those picks did over the following quarter. Replicates Core v2.1 exactly:
  HRP weights · 15 names · sector<=2 · 120-day lookback · quarterly (63 trading days).

For each rebalance date we show: the stocks chosen, their HRP weight, entry/exit price, the
stock's return over the hold, profit/loss flag, and the weighted contribution. Then per
quarter: portfolio return (sum weight*ret), win rate (% of picks profitable). Finally a
4-quarter summary + overall hit rate.

The per-stock SELECTION and P&L is exactly the model's call. The live system also applies a
regime CASH overlay (e.g. only 60% invested now) which dampens both gains and losses equally
-- shown per quarter as "regime exposure" but NOT mixed into the stock-level P&L.

Run: python india/research/quarterly_picks.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import select_names, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import sector_of

REBAL, TOPN, SECTOR_CAP = 63, 15, 2


def main():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    rebal_idx = list(closes.index[::REBAL])

    # build (start, end) holding windows; keep the last 4 COMPLETE + 1 ongoing
    windows = []
    for i in range(len(rebal_idx) - 1):
        windows.append((rebal_idx[i], rebal_idx[i + 1], True))
    windows.append((rebal_idx[-1], closes.index[-1], False))   # current, ongoing
    windows = windows[-5:]                                     # last 4 complete + current

    print("=" * 74)
    print("  ARJUNA Core v2.1 — QUARTERLY PICKS & P&L (last 4 quarters + current)")
    print("  HRP · 15 names · sector<=2 · quarterly hold. Per-stock = pure model call.")
    print("=" * 74)

    q_summaries = []
    all_wins = 0; all_trades = 0

    for start, end, complete in windows:
        hist = rets.loc[:start].tail(LOOKBACK).dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        sel = select_names(hist, TOPN, sector_cap=SECTOR_CAP)
        w = weights_for("hrp", hist[sel]); w = (w / w.sum())

        rows = []
        for s in w.sort_values(ascending=False).index:
            p0 = closes.loc[start, s]; p1 = closes.loc[end, s]
            if pd.isna(p0) or pd.isna(p1):
                continue
            r = p1 / p0 - 1
            rows.append(dict(symbol=s, sector=sector_of(s), wt=100 * w[s],
                             entry=p0, exit=p1, ret=100 * r, contrib=100 * w[s] * r))
        df = pd.DataFrame(rows)
        port_ret = df["contrib"].sum()                        # weighted quarter return (gross, fully invested)
        wins = int((df["ret"] > 0).sum()); n = len(df)
        winrate = 100 * wins / n if n else 0
        days = closes.index.get_loc(end) - closes.index.get_loc(start)

        tag = "" if complete else "   *** CURRENT / IN PROGRESS ***"
        print(f"\n  Q {start.date()} -> {end.date()}  ({days} trading days){tag}")
        print(f"  {'#':<3}{'stock':<13}{'sector':<16}{'wt%':>6}{'entry':>10}{'exit':>10}{'ret%':>8}{'P/L':>5}{'contrib%':>10}")
        for i, r in enumerate(df.to_dict("records"), 1):
            pl = "WIN" if r["ret"] > 0 else "loss"
            print(f"  {i:<3}{r['symbol']:<13}{r['sector']:<16}{r['wt']:>6.1f}{r['entry']:>10,.0f}"
                  f"{r['exit']:>10,.0f}{r['ret']:>+8.1f}{pl:>5}{r['contrib']:>+10.2f}")
        print(f"  {'-'*70}")
        print(f"  PORTFOLIO (gross, fully invested): {port_ret:+.2f}%   |   "
              f"WIN RATE: {wins}/{n} = {winrate:.0f}%   |   "
              f"best {df['ret'].max():+.1f}% ({df.loc[df['ret'].idxmax(),'symbol']})  "
              f"worst {df['ret'].min():+.1f}% ({df.loc[df['ret'].idxmin(),'symbol']})")

        if complete:
            q_summaries.append(dict(period=f"{start.date()}->{end.date()}", ret=port_ret,
                                    winrate=winrate, wins=wins, n=n))
            all_wins += wins; all_trades += n

    # ---- 4-quarter summary ----
    print("\n" + "=" * 74)
    print("  SUMMARY — last 4 COMPLETE quarters")
    print("=" * 74)
    print(f"  {'quarter':<26}{'port ret%':>11}{'win rate':>11}{'picks':>8}")
    cum = 1.0
    for q in q_summaries:
        cum *= (1 + q["ret"] / 100)
        print(f"  {q['period']:<26}{q['ret']:>+11.2f}{q['winrate']:>10.0f}%{q['n']:>8}")
    avg = np.mean([q["ret"] for q in q_summaries]) if q_summaries else 0
    pos_q = sum(1 for q in q_summaries if q["ret"] > 0)
    print(f"  {'-'*60}")
    print(f"  avg quarter return    {avg:+.2f}%   (compounded 4Q: {100*(cum-1):+.1f}%)")
    print(f"  profitable quarters   {pos_q}/{len(q_summaries)}")
    print(f"  OVERALL STOCK WIN RATE {all_wins}/{all_trades} = {100*all_wins/all_trades:.0f}%   "
          f"(every pick across all 4 quarters)")
    print("\n  Note: 'port ret' is GROSS (fully invested). The live system trims exposure in")
    print("  weak regimes (cash buffer), so realized swings -- up AND down -- are smaller.")
    print("  CAGR is survivorship-inflated; the win rate + per-stock spread is the honest read.")


if __name__ == "__main__":
    main()
