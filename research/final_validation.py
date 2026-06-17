# research/final_validation.py
"""
FINAL rigor gate on the VALIDATED config (regime-aware LONG+SHORT) for BOTH primary
instruments — XAUUSDm and BTCUSDm — not one. The last statistical check before paper.

Per pair / timeframe (OOS, net of cost):
  * Deflated Sharpe (multiple-testing-adjusted)   -> want > 0.90
  * PBO (probability of backtest overfitting)      -> want < 0.50
  * yearly walk-forward profitable-years           -> want most years positive
  -> GO (to paper) / NO-GO verdict.

Run: python research/final_validation.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, pipeline, gate
from strategy import playbook
from strategy.smc import ema, atr
from backtest.engine import backtest, BARS_PER_YEAR
from backtest.validator import deflated_sharpe_ratio, probability_of_backtest_overfitting
from backtest.trade_sim import trade_stats
from research.long_short_walkforward import both_sides

FOCUS = ["XAUUSDm", "BTCUSDm"]
N_TRIALS = pipeline().get("n_strategies_tried", 8)
G = gate()


def ls_position(df, reg, fast, slow):
    """Continuous long+short position: +1 bullish-trend, -1 bearish-trend, 0 otherwise."""
    f, s = ema(df["close"], fast), ema(df["close"], slow)
    trend = reg.reindex(df.index) == "trend"
    return pd.Series(np.where(trend & (f > s), 1.0, np.where(trend & (f < s), -1.0, 0.0)), index=df.index)


def run():
    print("=" * 90)
    print("  FINAL VALIDATION — regime-aware LONG+SHORT, both primary pairs (XAU + BTC)")
    print("=" * 90)
    for sym in FOCUS:
        for tf in ("H4", "H1"):
            p = ROOT / f"data/raw/{sym}_{tf}.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p).sort_index()
            sp = symbol_params(sym, df["close"])
            method = "hmm" if len(df) >= pipeline().get("hmm_min_bars", 6000) else "adx"
            reg = playbook.regime_labels(df, method)
            a = atr(df, 14)

            # Deflated Sharpe on the long+short signal (bar returns)
            net, _ = backtest(df, ls_position(df, reg, 20, 50), sp["cost"])
            dsr = float("nan")
            if len(net) > 2 and net.std() > 0:
                sr = net.mean() / net.std(); sk = net.skew(); ku = net.kurt() + 3
                sr_var = (1 - sk * sr + (ku - 1) / 4 * sr ** 2) / (len(net) - 1)
                dsr = deflated_sharpe_ratio(sr, len(net), N_TRIALS, sr_var, sk, ku)

            # PBO across EMA-param variants of the long+short
            variants = {"20/50": (20, 50), "10/30": (10, 30), "30/100": (30, 100), "50/200": (50, 200)}
            rmat = pd.DataFrame({k: backtest(df, ls_position(df, reg, fa, sl), sp["cost"])[0]
                                 for k, (fa, sl) in variants.items()}).dropna()
            pbo = probability_of_backtest_overfitting(rmat, n_splits=10)

            # yearly walk-forward profitable-years (full trade management, long+short)
            years = sorted(df.index.year.unique())[1:]
            bpy = BARS_PER_YEAR.get(tf, 252 * 24)
            pos_years = n_years = 0
            for ty in years:
                mask = df.index.year == ty
                if mask.sum() < 50 or df[df.index.year < ty].shape[0] < 1500:
                    continue
                tr = both_sides(df, mask, a, sp, reg, do_short=True)
                s = trade_stats(tr, bpy, tr["bars"].mean() if not tr.empty else 1)
                if s:
                    n_years += 1; pos_years += s["total"] > 0

            ann = (net.mean() / net.std() * np.sqrt(BARS_PER_YEAR.get(tf, 252 * 24))) if net.std() > 0 else 0
            yr_ok = n_years and pos_years / n_years >= 0.6
            verdict = ("GO -> paper" if (dsr or 0) >= G["min_dsr"] and (np.isnan(pbo) or pbo < G["max_pbo"]) and yr_ok
                       else "NOT READY")
            print(f"\n  {sym} {tf} [{method.upper()}]")
            print(f"    annualised Sharpe (signal) : {ann:>5.2f}")
            print(f"    Deflated Sharpe            : {dsr:.2f}   (want > {G['min_dsr']})")
            print(f"    PBO (overfit prob)         : {pbo:.2f}   (want < {G['max_pbo']})")
            print(f"    walk-forward years +ve     : {pos_years}/{n_years}")
            print(f"    => {verdict}")


if __name__ == "__main__":
    run()
