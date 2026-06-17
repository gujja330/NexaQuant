# research/smc_probe.py
"""
Honest test of Smart Money Concepts (SMC) + FVG on every symbol in data/raw.

Two-part evidence (same discipline as edge_probe.py):
  PART A  Event study  -- after each SMC signal fires, what is the average forward
          return vs the unconditional baseline? If a pattern has no edge, its
          forward return ~= baseline. (Pure leakage-free statistics, no costs.)
  PART B  Strategy backtest -- run the SMC positional signals through the shared
          cost-aware engine, IS/OOS, benchmarked against buy&hold and EMA trend.

Symbol-agnostic: tests XAUUSDm now; auto-includes BTCUSDm the moment its parquet
files are dropped into data/raw (pull from MT5 -- see data/prepare_data.py).

Run: python research/smc_probe.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.engine import backtest, stats, print_row, HEADER
from strategy.smc import (market_structure, fair_value_gaps, liquidity_sweep,
                          order_blocks, premium_discount, sig_fvg_trend,
                          sig_sweep_reversal, sig_smc_confluence, sig_smc_a_plus, ema)

RAW = "data/raw"
COST = {"XAUUSDm": 0.50, "BTCUSDm": 5.0}   # $ round trip; BTC spread far wider
TFS = ["H1", "H4"]
IS_FRACTION = 0.70
FWD = 12   # forward bars for event study


def discover():
    syms = {}
    for f in glob.glob(f"{RAW}/*_H1.parquet"):
        m = re.match(r"(.+)_H1\.parquet", os.path.basename(f))
        if m:
            syms.setdefault(m.group(1), True)
    return sorted(syms)


def event_study(df):
    """Average forward FWD-bar return ($/unit) conditional on each SMC signal."""
    fwd = df["close"].shift(-FWD) - df["close"]
    base = fwd.dropna()
    f = fair_value_gaps(df)
    st = market_structure(df)
    bull_sweep, _ = liquidity_sweep(df)
    ob = order_blocks(df)
    pd_ = premium_discount(df)
    bos_up = (st == 1) & (st.shift(1) != 1)
    discount_up = (st == 1) & (pd_["zone"] == 1)             # bullish struct + discount
    deep_disc_up = (st == 1) & (pd_["deep"] == 1)            # bullish struct + deep discount
    rows = [("baseline (all bars)", base)]
    rows.append(("after bullish FVG forms", fwd[f["bull"]].dropna()))
    rows.append(("after bullish liq. sweep", fwd[bull_sweep].dropna()))
    rows.append(("after bullish BOS", fwd[bos_up].dropna()))
    rows.append(("discount zone + bull struct", fwd[discount_up].dropna()))
    rows.append(("DEEP discount + bull struct", fwd[deep_disc_up].dropna()))
    print(f"    {'signal':<28}{'n':>7}{'mean_fwd$':>11}{'win%>0':>9}{'edge vs base':>14}")
    bmean = base.mean()
    for name, s in rows:
        if len(s) == 0:
            continue
        edge = s.mean() - bmean
        tag = "" if name.startswith("baseline") else f"{edge:+.2f}"
        print(f"    {name:<28}{len(s):>7}{s.mean():>11.2f}{100*(s>0).mean():>8.1f}%{tag:>14}")


def run():
    syms = discover()
    print(f"Symbols found in {RAW}: {syms}")
    if "BTCUSDm" not in syms:
        print("  (BTCUSDm not present -> pull H1/H4 from MT5 to auto-include it.)\n")

    for sym in syms:
        cost = COST.get(sym, 0.5)
        for tf in TFS:
            p = f"{RAW}/{sym}_{tf}.parquet"
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p).sort_index()
            notional = df["close"].iloc[0]
            split = int(len(df) * IS_FRACTION)
            print("=" * 104)
            print(f"  {sym}  {tf}   bars={len(df)}   {df.index[0].date()}->{df.index[-1].date()}"
                  f"   cost=${cost}/unit   (SMC proxy on {tf}; true SMC wants M5/M15)")
            print("=" * 104)

            print("  PART A -- EVENT STUDY (forward {}-bar return after signal):".format(FWD))
            event_study(df)

            print("\n  PART B -- STRATEGY BACKTEST:")
            print("  " + HEADER)
            builders = {
                "Buy & hold":              lambda d: pd.Series(1.0, index=d.index),
                "EMA 20/50 trend (ref)":   lambda d: pd.Series(np.where(ema(d["close"],20)>ema(d["close"],50),1,0), index=d.index),
                "SMC: FVG + structure":    lambda d: sig_fvg_trend(d, long_only=True),
                "SMC: liquidity sweep":    sig_sweep_reversal,
                "SMC: full confluence":    sig_smc_confluence,
                "SMC: A+ (5-pillar)":      sig_smc_a_plus,
            }
            for name, fn in builders.items():
                for seg, sl in (("IS", slice(0, split)), ("OOS", slice(split, None))):
                    seg_df = df.iloc[sl]
                    net, tr = backtest(seg_df, fn(seg_df), cost)
                    print_row("  " + name, seg, stats(net, tr, notional, tf))
                print()


if __name__ == "__main__":
    run()
