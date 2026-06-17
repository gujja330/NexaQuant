# research/regime_gated_probe.py
"""
THE core test: does a REGIME GATE turn our signals into better risk-adjusted profit?

Our prior findings:
  - continuation (EMA/FVG/structure) wins in trends
  - mean-reversion (discount buys) loses in trends -> should only fire in ranges
  - volatility expansion is dangerous -> stand aside

This probe compares, on the SAME data, net of cost, IS vs OOS:
  1. Baseline          : continuation long, ALWAYS on (ungated)
  2. Gated continuation: continuation long ONLY in trend regime (flat else)
  3. Regime-switched   : trend->continuation, range->mean-revert, volatile/neutral->flat
  4. Switched + sizing : (3) scaled by volatility-targeted position sizing

Hypothesis to confirm/refute: gating + sizing reduces drawdown and lifts Sharpe.

Run: python research/regime_gated_probe.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.engine import backtest, stats, print_row, HEADER
from strategy.regime import detect_regime, regime_summary
from strategy.risk import vol_target_size
from strategy.smc import ema, premium_discount

RAW = "data/raw"
COST = {"XAUUSDm": 0.50, "BTCUSDm": 5.0}
TFS = ["H1", "H4"]
IS_FRACTION = 0.70


def cfg():
    with open(Path(__file__).resolve().parents[1] / "config" / "base_config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(f"{RAW}/*_H1.parquet")})


def build(df, reg_kw, size_kw):
    reg, _, _ = detect_regime(df, **reg_kw)
    cont = (ema(df["close"], 20) > ema(df["close"], 50)).astype(float)        # continuation long
    mr = (premium_discount(df)["zone"] == 1).astype(float)                     # range mean-revert long
    size = vol_target_size(df, atr_n=size_kw["atr_n"], ref_window=size_kw["ref_window"],
                           cap=size_kw["cap"], floor=size_kw["floor"])
    is_trend, is_range = (reg == "trend"), (reg == "range")
    switched = pd.Series(0.0, index=df.index)
    switched[is_trend] = cont[is_trend]
    switched[is_range] = mr[is_range]
    return {
        "1 Baseline (always-on)":     cont,
        "2 Gated continuation":       cont.where(is_trend, 0.0),
        "3 Regime-switched":          switched,
        "4 Switched + vol-sizing":    switched * size,
    }, reg


def run():
    c = cfg()
    reg_kw = c.get("regime", {})
    size_kw = c.get("sizing", {"atr_n": 14, "ref_window": 200, "cap": 3.0, "floor": 0.25})
    syms = discover()
    print(f"Symbols: {syms}   (BTCUSDm auto-included once pulled via data/pull_mt5.py)\n")

    for sym in syms:
        cost = COST.get(sym, 0.5)
        for tf in TFS:
            p = f"{RAW}/{sym}_{tf}.parquet"
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p).sort_index()
            notional = df["close"].iloc[0]
            split = int(len(df) * IS_FRACTION)
            variants, reg = build(df, reg_kw, size_kw)
            print("=" * 104)
            print(f"  {sym}  {tf}   bars={len(df)}   regime mix: {regime_summary(reg)}   cost=${cost}")
            print("=" * 104)
            print("  " + HEADER)
            for name, pos in variants.items():
                for seg, sl in (("IS", slice(0, split)), ("OOS", slice(split, None))):
                    seg_df = df.iloc[sl]
                    net, tr = backtest(seg_df, pos.iloc[sl], cost)
                    print_row("  " + name, seg, stats(net, tr, notional, tf))
                print()


if __name__ == "__main__":
    run()
