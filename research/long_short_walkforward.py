# research/long_short_walkforward.py
"""
Does REGIME-AWARE LONG+SHORT fix the bear-year losses?

The long-only trend-follower bleeds in downtrends (e.g. crypto 2022). The fix: go LONG in
bullish-trend regimes and SHORT in bearish-trend regimes (both already in the playbook).
This runs the anchored yearly walk-forward for LONG-ONLY vs LONG+SHORT, side by side, so
we can see whether adding shorts turns losing bear years positive.

Focus: BTCUSDm (has the 2022 bear) and XAUUSDm. Out-of-sample by year, net of cost.

Run: python research/long_short_walkforward.py
"""
import sys, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, pipeline
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import simulate_trades, trade_stats
from backtest.engine import BARS_PER_YEAR

RAW = ROOT / "data" / "raw"
HMM_MIN = pipeline().get("hmm_min_bars", 6000)
FOCUS = ["BTCUSDm", "XAUUSDm"]


def both_sides(df, mask, a, sp, reg, do_short):
    """Combined long (+ optional short) trades over the bars selected by `mask`."""
    seg = df[mask]
    parts = []
    lent = playbook.entries(df, side="long", regime=reg)
    lex = playbook.momentum_exit_signal(df, side="long")
    parts.append(simulate_trades(seg, lent[mask], a[mask], sp["cost"],
                                 exit_signal=lex[mask], pip_size=sp["pip_size"], side=1, **playbook.EXIT))
    if do_short:
        sent = playbook.entries(df, side="short", regime=reg)
        sex = playbook.momentum_exit_signal(df, side="short")
        parts.append(simulate_trades(seg, sent[mask], a[mask], sp["cost"],
                                     exit_signal=sex[mask], pip_size=sp["pip_size"], side=-1, **playbook.EXIT))
    tr = pd.concat([p for p in parts if not p.empty]) if any(not p.empty for p in parts) else parts[0]
    return tr.sort_values("entry_time") if not tr.empty else tr


def run():
    for sym in FOCUS:
        for tf in ("H4", "H1"):
            p = RAW / f"{sym}_{tf}.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p).sort_index()
            sp = symbol_params(sym, df["close"]); bpy = BARS_PER_YEAR.get(tf, 252 * 24)
            method = "hmm" if len(df) >= HMM_MIN else "adx"
            reg = playbook.regime_labels(df, method)
            a = atr(df, 14)
            years = sorted(df.index.year.unique())[1:]
            print("\n" + "=" * 92)
            print(f"  LONG-ONLY vs LONG+SHORT — {sym} {tf} ({method.upper()})  anchored yearly walk-forward")
            print("=" * 92)
            print(f"    {'test yr':<8}| {'LONG-ONLY ret%':>15}{'Sh':>7} | {'LONG+SHORT ret%':>16}{'Sh':>7}{'trades':>8}")
            lo_pos = ls_pos = n = 0
            for ty in years:
                mask = df.index.year == ty
                if mask.sum() < 50 or df[df.index.year < ty].shape[0] < 1500:
                    continue
                notional = df[mask]["close"].iloc[0]
                lo = both_sides(df, mask, a, sp, reg, do_short=False)
                ls = both_sides(df, mask, a, sp, reg, do_short=True)
                slo = trade_stats(lo, bpy, lo["bars"].mean() if not lo.empty else 1)
                sls = trade_stats(ls, bpy, ls["bars"].mean() if not ls.empty else 1)
                lo_ret = 100 * slo["total"] / notional if slo else 0
                ls_ret = 100 * sls["total"] / notional if sls else 0
                lo_sh = slo["sharpe"] if slo else 0
                ls_sh = sls["sharpe"] if sls else 0
                n += 1; lo_pos += lo_ret > 0; ls_pos += ls_ret > 0
                print(f"    {ty:<8}| {lo_ret:>15.1f}{lo_sh:>7.1f} | {ls_ret:>16.1f}{ls_sh:>7.1f}"
                      f"{(sls['trades'] if sls else 0):>8}")
            if n:
                print(f"    => profitable years: LONG-ONLY {lo_pos}/{n}   LONG+SHORT {ls_pos}/{n}")


if __name__ == "__main__":
    run()
