# research/hmm_regime_probe.py
"""
Does a LEARNED (HMM) regime gate beat the rule-based (ADX) gate?

Same entry edge (continuation longs) + same momentum-ride exit; the ONLY difference is
which regime detector decides "is this a trend regime?". Compared OOS, net of cost.

HMM is fit causally (params on in-sample only; states via forward filter) so this is a
fair, leakage-safe comparison.

Run: python research/hmm_regime_probe.py
"""
import sys, glob, os, re
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.trade_sim import simulate_trades, trade_stats
from strategy.smc import ema, atr
from strategy.regime import detect_regime, detect_regime_hmm, regime_summary

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
            cont = ema(df["close"], 20) > ema(df["close"], 50)
            mom = df["close"] < ema(df["close"], 20)
            a = atr(df, 14)

            reg_adx, _, _ = detect_regime(df)
            reg_hmm = detect_regime_hmm(df, fit_fraction=IS_FRACTION)

            print("=" * 86)
            print(f"  HMM vs ADX regime gate - {sym} {tf}")
            print(f"    ADX mix: {regime_summary(reg_adx)}")
            print(f"    HMM mix: {regime_summary(reg_hmm)}")
            print("=" * 86)
            print(f"    {'gate (OOS)':<14}{'n':>4}{'win%':>6}{'avgR':>6}{'payoff':>7}"
                  f"{'PF':>6}{'tot$':>8}{'maxDD':>7}{'Sharpe':>8}")
            for name, reg in (("ADX gate", reg_adx), ("HMM gate", reg_hmm)):
                ok = (cont & (reg == "trend")).astype(bool)
                ent = (ok & (~ok.shift(1, fill_value=False))).iloc[split:]
                oos = df.iloc[split:]
                tr = simulate_trades(oos, ent, a.iloc[split:], cost,
                                     stop_mult=2.0, partial_at=1.5, partial_frac=0.4,
                                     exit_signal=mom.iloc[split:])
                s = trade_stats(tr, bpy, tr["bars"].mean() if not tr.empty else 1)
                if s:
                    print(f"    {name:<14}{s['trades']:>4}{100*s['win']:>6.0f}{s['avgR']:>6.2f}"
                          f"{s['payoff']:>7.2f}{s['pf']:>6.2f}{s['total']:>8.1f}{s['dd']:>7.1f}{s['sharpe']:>8.2f}")
                else:
                    print(f"    {name:<14}(no trades)")
            print()


if __name__ == "__main__":
    run()
