# research/validation_runner.py
"""
Run our candidate edges through the RIGOR GATE (backtest/validator.py):
  1. Walk-forward stability of the regime-gated continuation strategy (does the edge
     persist across time folds, or did one bull window flatter it?).
  2. Deflated Sharpe of the headline OOS result (is it real after multiple-testing?).
  3. CPCV of the AI meta-labeler (distribution of OOS AUC + selected-trade PnL).

This is the honest verdict layer: only what survives here earns capital.

Run: python research/validation_runner.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.engine import backtest, stats, BARS_PER_YEAR
from backtest.validator import (walk_forward, deflated_sharpe_ratio,
                                probabilistic_sharpe_ratio, cpcv_metalabel)
from strategy.smc import ema
from strategy.regime import detect_regime
from strategy.meta_label import build_features, triple_barrier_labels

RAW = "data/raw"
COST = {"XAUUSDm": 0.50, "BTCUSDm": 5.0}
TFS = {"H1": 24, "H4": 12}
N_STRATEGIES_TRIED = 8   # honest count of distinct strategies we backtested (for DSR)


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(f"{RAW}/*_H1.parquet")})


def gated_continuation(df):
    reg, _, _ = detect_regime(df)
    cont = (ema(df["close"], 20) > ema(df["close"], 50)).astype(float)
    return cont.where(reg == "trend", 0.0)


def run():
    for sym in discover():
        cost = COST.get(sym, 0.5)
        for tf, horizon in TFS.items():
            p = f"{RAW}/{sym}_{tf}.parquet"
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p).sort_index()
            print("\n" + "=" * 90)
            print(f"  VALIDATION - {sym} {tf}   bars={len(df)}   cost=${cost}")
            print("=" * 90)

            # 1) walk-forward stability
            res, summ = walk_forward(df, gated_continuation, cost, tf, n_folds=6)
            print("  [1] Walk-forward stability (regime-gated continuation):")
            for _, r in res.iterrows():
                print(f"      fold {int(r['fold'])}  {r['from']}->{r['to']}  "
                      f"trades={int(r['trades']):>3}  Sharpe={r['sharpe']:>6.2f}  total=${r['total']:>7.1f}")
            print(f"      => mean Sharpe {summ['mean_sharpe']:.2f} +/- {summ['std_sharpe']:.2f}, "
                  f"{summ['pct_folds_positive']:.0%} folds positive, worst {summ['worst_fold_sharpe']:.2f}")

            # 2) deflated Sharpe of full-sample result
            net, tr = backtest(df, gated_continuation(df), cost)
            if len(net) > 2 and net.std() > 0:
                sr = net.mean() / net.std()                       # per-bar Sharpe
                skew = net.skew(); kurt = net.kurt() + 3
                psr = probabilistic_sharpe_ratio(sr, len(net), skew, kurt)
                # variance of the Sharpe-ratio ESTIMATOR (Lo, 2002 / Bailey-LdP), per-bar units
                sr_var = (1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2) / (len(net) - 1)
                dsr = deflated_sharpe_ratio(sr, len(net), N_STRATEGIES_TRIED,
                                            sharpe_variance=sr_var, skew=skew, kurt=kurt)
                ann = sr * np.sqrt(BARS_PER_YEAR[tf])
                print(f"  [2] Deflated Sharpe: annualised={ann:.2f}  PSR(>0)={psr:.2f}  "
                      f"DSR(vs {N_STRATEGIES_TRIED} trials)={dsr:.2f}   "
                      f"{'PASS' if (dsr or 0) > 0.95 else 'NOT robust'}")

            # 3) CPCV of the meta-labeler
            reg, _, _ = detect_regime(df)
            base = ((ema(df["close"], 20) > ema(df["close"], 50)) & (reg == "trend")).astype(bool)
            entries = base & (~base.shift(1, fill_value=False))
            cp = cpcv_metalabel(df, entries, horizon, build_features, triple_barrier_labels,
                                sym, tf, n_groups=8, k_test=2)
            if cp is None:
                print("  [3] CPCV meta-labeler: insufficient samples (need more data)")
            else:
                print(f"  [3] CPCV meta-labeler ({cp['n_paths']} paths): "
                      f"AUC median={cp['auc_median']:.3f}, {cp['auc_pct_above_0.55']:.0%} paths>0.55; "
                      f"selected-trade PnL positive in {cp['sel_pnl_pct_positive']:.0%} of paths")
                verdict = "skill" if (cp['auc_median'] > 0.55 and cp['sel_pnl_pct_positive'] > 0.6) else "NO skill yet"
                print(f"      => verdict: {verdict}")


if __name__ == "__main__":
    run()
