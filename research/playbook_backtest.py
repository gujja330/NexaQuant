# research/playbook_backtest.py
"""
End-to-end backtest of the CANONICAL NexaQuant playbook (strategy/playbook.py):
regime-gated continuation entry  +  ATR stop  +  momentum-ride exit  +  scale-out.

This is the single "this is the strategy" run. IS vs OOS, net of cost.

Run: python research/playbook_backtest.py
"""
import sys, glob, os, re
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.trade_sim import simulate_trades, trade_stats
from strategy.smc import atr
from strategy import playbook

RAW = "data/raw"
COST = {"XAUUSDm": 0.50, "BTCUSDm": 5.0}
TFS = {"H1": 24 * 252, "H4": 6 * 252}
IS_FRACTION = 0.70


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(f"{RAW}/*_H1.parquet")})


def run():
    for sym in discover():
        cost = COST.get(sym, 0.5)
        for tf, bpy in TFS.items():
            p = f"{RAW}/{sym}_{tf}.parquet"
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p).sort_index()
            split = int(len(df) * IS_FRACTION)
            a_full = atr(df, 14)
            ex_full = playbook.momentum_exit_signal(df)        # full-series, then sliced
            print("=" * 96)
            print(f"  PLAYBOOK — {sym} {tf}  (entry: regime-gated continuation; exit: ATR stop + momentum-ride + scale-out)")
            print("=" * 96)
            print(f"    {'gate / seg':<16}{'n':>4}{'win%':>6}{'avgR':>6}{'payoff':>7}{'avgWin$':>8}"
                  f"{'maxR':>6}{'PF':>6}{'tot$':>8}{'maxDD':>7}{'Sharpe':>8}")
            for method in ("adx", "hmm"):
                reg = playbook.regime_labels(df, method)        # full series (HMM fit on IS only)
                ent_full = playbook.entries(df, regime=reg)
                for seg, sl in (("IS", slice(0, split)), ("OOS", slice(split, None))):
                    sd = df.iloc[sl]
                    tr = simulate_trades(sd, ent_full.iloc[sl], a_full.iloc[sl], cost,
                                         exit_signal=ex_full.iloc[sl], **playbook.EXIT)
                    s = trade_stats(tr, bpy, tr["bars"].mean() if not tr.empty else 1)
                    tag = f"{method.upper()} {seg}"
                    if s:
                        print(f"    {tag:<16}{s['trades']:>4}{100*s['win']:>6.0f}{s['avgR']:>6.2f}"
                              f"{s['payoff']:>7.2f}{s['avg_win']:>8.1f}{s['max_R']:>6.1f}{s['pf']:>6.2f}"
                              f"{s['total']:>8.1f}{s['dd']:>7.1f}{s['sharpe']:>8.2f}")
                    else:
                        print(f"    {tag:<16}(no trades)")
                print()


if __name__ == "__main__":
    run()
