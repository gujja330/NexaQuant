# research/pair_compare.py
"""
WHICH PAIR/INSTRUMENT is best — rank every symbol in data/raw and pick the winner.

Apples-to-apples: each symbol runs through the canonical playbook on a COMMON timeframe
(default H1) so pairs are comparable; we also report each pair's own BEST timeframe.
Ranked by PROFIT (return %, profit factor) + SAFETY (win%) + RISK (drawdown %, Sharpe).

Efficient: every (symbol, timeframe) is evaluated ONCE and cached.

Run: python research/pair_compare.py            # common TF = H1
     python research/pair_compare.py H4
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.timeframe_compare import evaluate, discover
from config_loader import timeframes

_CACHE = {}


def ev(sym, tf):
    if (sym, tf) not in _CACHE:
        _CACHE[(sym, tf)] = evaluate(sym, tf)
    return _CACHE[(sym, tf)]


def run(common_tf="H1"):
    syms = discover()
    print("\n" + "#" * 92)
    print(f"#  PAIR / INSTRUMENT RANKING  (common timeframe = {common_tf}, OOS, net of cost)")
    print("#" * 92)
    rows = []
    for s in syms:
        r = ev(s, common_tf)
        if r:
            r = {**r, "symbol": s}; rows.append(r)
    if not rows:
        print("  no symbols with data on this timeframe."); return
    df = pd.DataFrame(rows)
    df["profit_rank"] = df[["ret_pct", "pf", "avgR"]].rank().mean(axis=1)
    df["safety_rank"] = df[["win", "pf"]].rank().mean(axis=1)
    df["risk_rank"] = df[["dd_pct"]].rank(ascending=False).mean(axis=1) + df[["sharpe"]].rank().mean(axis=1)
    df["overall"] = df[["profit_rank", "safety_rank", "risk_rank"]].mean(axis=1)
    df = df.sort_values("overall", ascending=False)
    print(f"  {'symbol':<10}{'trades':>7}{'win%':>6}{'ret%':>8}{'PF':>6}{'avgR':>6}{'maxDD%':>8}{'Sharpe':>8}")
    for _, r in df.iterrows():
        print(f"  {r['symbol']:<10}{int(r['trades']):>7}{100*r['win']:>5.0f}%{r['ret_pct']:>8.1f}"
              f"{r['pf']:>6.2f}{r['avgR']:>6.2f}{r['dd_pct']:>7.1f}%{r['sharpe']:>8.2f}")
    win = df.iloc[0]
    print(f"\n  >> BEST PAIR: {win['symbol']}  (Sharpe {win['sharpe']:.2f}, return {win['ret_pct']:.1f}%, "
          f"win {100*win['win']:.0f}%, maxDD {win['dd_pct']:.1f}%)")
    print("  Per-pair best timeframe:")
    for s in df["symbol"]:
        cand = [ev(s, tf) for tf in timeframes()]
        cand = [c for c in cand if c and c["trades"] >= 10]
        if cand:
            b = max(cand, key=lambda c: c["sharpe"])
            print(f"    {s:<10}-> {b['tf']}  (Sharpe {b['sharpe']:.2f}, {int(b['trades'])} trades, DD {b['dd_pct']:.1f}%)")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "H1")
