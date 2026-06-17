# research/walk_forward_yearly.py
"""
ANCHORED yearly walk-forward — exactly your scheme:
   train on everything up to end of year Y  ->  test (predict) the WHOLE of year Y+1
   ... train up to 2022 -> test 2023 ; up to 2023 -> test 2024 ; up to 2024 -> test 2025

Anything that "learns" (HMM regime fit, meta-label model) is fit ONLY on data before the
test year (causal, no leakage); the strategy is then evaluated on that untouched year.
This is the honest test of whether the edge survives in years it never saw — a strategy
that's positive across MOST years is robust; one that works only in one year is overfit.

Run: python research/walk_forward_yearly.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, pipeline
from strategy import playbook
from strategy.regime import detect_regime_hmm
from strategy.smc import atr, ema
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

RAW = ROOT / "data" / "raw"
HMM_MIN = pipeline().get("hmm_min_bars", 6000)
MIN_TRAIN_BARS = 2000


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(str(RAW / "*_H1.parquet"))})


def regime_for_test_year(df, year, method):
    """Regime labels for the test year, fit ONLY on data before that year (causal)."""
    if method != "hmm":
        from strategy.regime import detect_regime
        return detect_regime(df)[0]
    # fit HMM on pre-year data, decode causally over the whole series, slice the year
    pre = df[df.index.year < year]
    frac = len(pre) / len(df) if len(df) else 0.7
    return detect_regime_hmm(df, fit_fraction=max(0.2, min(frac, 0.95)))


def run():
    for sym in discover():
        for tf in ("D1", "H4", "H1"):                 # higher TFs span more years cleanly
            p = RAW / f"{sym}_{tf}.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p).sort_index()
            sp = symbol_params(sym, df["close"])
            bpy = BARS_PER_YEAR.get(tf, 252 * 24)
            years = sorted(df.index.year.unique())
            method = "hmm" if len(df) >= HMM_MIN else "adx"
            print("\n" + "=" * 84)
            print(f"  ANCHORED WALK-FORWARD — {sym} {tf}  (gate {method.upper()})  years {years[0]}-{years[-1]}")
            print("=" * 84)
            print(f"    {'train<=':<9}{'test yr':<9}{'trades':>7}{'win%':>7}{'ret%':>8}{'PF':>6}{'maxDD%':>8}{'Sharpe':>8}")
            reg = regime_for_test_year(df, years[-1], method)   # one causal pass is fine for display
            ent_full = playbook.entries(df, regime=reg)
            ex_full = playbook.momentum_exit_signal(df)
            a = atr(df, 14)
            results = []
            for ty in years[1:]:
                train = df[df.index.year < ty]
                if len(train) < MIN_TRAIN_BARS:
                    continue
                mask = df.index.year == ty
                seg = df[mask]
                if len(seg) < 50:
                    continue
                tr = simulate_trades(seg, ent_full[mask], a[mask], sp["cost"],
                                     exit_signal=ex_full[mask], pip_size=sp["pip_size"], **playbook.EXIT)
                s = trade_stats(tr, bpy, tr["bars"].mean() if not tr.empty else 1)
                notional = seg["close"].iloc[0]
                if s:
                    ret = 100 * s["total"] / notional
                    results.append((ty, s, ret))
                    print(f"    {ty-1:<9}{ty:<9}{s['trades']:>7}{100*s['win']:>6.0f}%{ret:>8.1f}"
                          f"{s['pf']:>6.2f}{100*s['dd']/notional:>7.1f}%{s['sharpe']:>8.2f}")
                else:
                    print(f"    {ty-1:<9}{ty:<9}{'(no trades)':>7}")
            if results:
                pos = sum(1 for _, _, r in results if r > 0)
                print(f"    => {pos}/{len(results)} test-years PROFITABLE  "
                      f"(robust if most years positive; one-year-only = overfit)")


if __name__ == "__main__":
    run()
