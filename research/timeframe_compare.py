# research/timeframe_compare.py
"""
WHICH TIMEFRAME is best to trade — ranked by PROFIT, SAFETY, and RISK.

Runs the canonical playbook on EVERY timeframe present for each symbol (M5/M15/H1/H4/D1)
and scores them so we can pick the best chart objectively rather than by assumption.

Metrics per timeframe (out-of-sample, net of cost):
  PROFIT : total return %, profit factor, avg R, net pips
  SAFETY : win rate, % of trades that are wins, expectancy
  RISK   : max drawdown %, worst trade R, Sharpe (risk-adjusted)
Then a composite rank + an honest conclusion (note: lower TF != automatically better —
more trades but more noise & cost drag; the data decides).

Run: python research/timeframe_compare.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, timeframes, pipeline
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

RAW = ROOT / "data" / "raw"
IS_FRACTION = pipeline().get("is_fraction", 0.70)
HMM_MIN = pipeline().get("hmm_min_bars", 6000)


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(str(RAW / "*_H1.parquet"))})


def evaluate(sym, tf):
    p = RAW / f"{sym}_{tf}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p).sort_index()
    sp = symbol_params(sym, df["close"])
    method = "hmm" if len(df) >= HMM_MIN else "adx"
    reg = playbook.regime_labels(df, method)
    ent = playbook.entries(df, regime=reg)
    ex = playbook.momentum_exit_signal(df)
    oos = slice(int(len(df) * IS_FRACTION), None)
    tr = simulate_trades(df.iloc[oos], ent.iloc[oos], atr(df, 14).iloc[oos], sp["cost"],
                         exit_signal=ex.iloc[oos], pip_size=sp["pip_size"], **playbook.EXIT)
    s = trade_stats(tr, BARS_PER_YEAR.get(tf, 252 * 24), tr["bars"].mean() if not tr.empty else 1)
    if not s:
        return None
    notional = df["close"].iloc[int(len(df) * IS_FRACTION)]
    ret_pct = 100 * s["total"] / notional
    worst_R = tr["R"].min()
    return dict(tf=tf, method=method, trades=s["trades"], win=s["win"], pf=s["pf"],
                avgR=s["avgR"], ret_pct=ret_pct, dd_pct=100 * s["dd"] / notional,
                worst_R=worst_R, sharpe=s["sharpe"], pips=s["total_pips"])


def run():
    order = list(timeframes())                       # M5,M15,H1,H4,D1
    for sym in discover():
        rows = [r for tf in order for r in [evaluate(sym, tf)] if r]
        if not rows:
            continue
        df = pd.DataFrame(rows)
        # composite scores (rank each metric; higher=better). RISK lower dd/worst better.
        df["profit_rank"] = df[["ret_pct", "pf", "avgR"]].rank().mean(axis=1)
        df["safety_rank"] = df[["win", "pf"]].rank().mean(axis=1)
        df["risk_rank"] = df[["dd_pct"]].rank(ascending=False).mean(axis=1) + df[["sharpe"]].rank().mean(axis=1)
        df["overall"] = df[["profit_rank", "safety_rank", "risk_rank"]].mean(axis=1)
        df = df.sort_values("overall", ascending=False)
        print("\n" + "#" * 88)
        print(f"#  {sym}  — TIMEFRAME COMPARISON (OOS, net of cost)")
        print("#" * 88)
        print(f"  {'TF':<5}{'gate':<5}{'trades':>7}{'win%':>6}{'ret%':>8}{'PF':>6}{'avgR':>6}"
              f"{'maxDD%':>8}{'worstR':>7}{'Sharpe':>8}")
        for _, r in df.iterrows():
            print(f"  {r['tf']:<5}{r['method']:<5}{int(r['trades']):>7}{100*r['win']:>5.0f}%"
                  f"{r['ret_pct']:>8.1f}{r['pf']:>6.2f}{r['avgR']:>6.2f}{r['dd_pct']:>7.1f}%"
                  f"{r['worst_R']:>7.1f}{r['sharpe']:>8.2f}")
        best_overall = df.iloc[0]
        best_profit = df.loc[df["ret_pct"].idxmax()]
        safest = df.loc[df["dd_pct"].idxmin()]
        print("\n  CONCLUSION:")
        print(f"    Best overall (profit+safety+risk): {best_overall['tf']}  (Sharpe {best_overall['sharpe']:.2f}, "
              f"DD {best_overall['dd_pct']:.1f}%, win {100*best_overall['win']:.0f}%)")
        print(f"    Most profit                      : {best_profit['tf']}  ({best_profit['ret_pct']:.1f}% OOS)")
        print(f"    Lowest risk (smallest drawdown)  : {safest['tf']}  (maxDD {safest['dd_pct']:.1f}%)")
        small = df.sort_values("trades", ascending=False).iloc[0]
        print(f"    Most trades (activity)           : {small['tf']}  ({int(small['trades'])} trades)")
        print("    NOTE: lower TF = more trades but more noise + cost drag; the table (not the")
        print("          assumption) decides. Few-trade TFs are statistically less reliable.")


if __name__ == "__main__":
    run()
