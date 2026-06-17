# research/meta_label_probe.py
"""
Test the AI meta-labeling layer: does filtering rules-based entries by the model's
P(win) improve out-of-sample, net-of-cost performance vs taking every entry?

Base signal: continuation long, fired in the TREND regime (our validated edge).
For each entry -> triple-barrier outcome. Train HistGradientBoosting on the in-sample
entries (with embargo), score the out-of-sample entries, then compare:
    ALL entries           vs    only entries with P(win) >= threshold

Reports OOS trade count, win%, expectancy, profit factor, total, max drawdown,
per-trade Sharpe, plus model AUC and the top feature importances.

Run: python research/meta_label_probe.py
"""
import sys, glob, os, re
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategy.smc import ema
from strategy.regime import detect_regime
from strategy.meta_label import build_features, triple_barrier_labels, train_eval

RAW = "data/raw"
COST = {"XAUUSDm": 0.50, "BTCUSDm": 5.0}
TFS = {"H1": 24, "H4": 12}        # tf -> triple-barrier horizon (bars)
IS_FRACTION = 0.70
THRESHOLD = 0.55                  # take trade only if P(win) >= this


def discover():
    return sorted({re.match(r"(.+)_H1\.parquet", os.path.basename(f)).group(1)
                   for f in glob.glob(f"{RAW}/*_H1.parquet")})


def trade_stats(pnls, cost, bars_per_year, horizon):
    if len(pnls) == 0:
        return None
    net = pnls - cost
    eq = net.cumsum()
    dd = (eq.cummax() - eq).max()
    wins = net > 0
    gl = -net[~wins].sum()
    pf = net[wins].sum() / gl if gl > 0 else np.inf
    # per-trade Sharpe annualized by average trade frequency
    trades_per_year = bars_per_year / max(horizon, 1)
    sharpe = (net.mean() / net.std()) * np.sqrt(trades_per_year) if net.std() > 0 else 0.0
    return dict(trades=len(net), win=wins.mean(), exp=net.mean(), pf=pf,
                total=eq.iloc[-1], dd=dd, sharpe=sharpe)


def show(tag, s):
    if s is None:
        print(f"    {tag:<26}(no trades)")
    else:
        print(f"    {tag:<26}{s['trades']:>6}{100*s['win']:>7.1f}{s['exp']:>9.2f}"
              f"{s['pf']:>7.2f}{s['total']:>10.1f}{s['dd']:>9.1f}{s['sharpe']:>8.2f}")


def run():
    bpy = {"H1": 24 * 252, "H4": 6 * 252}
    for sym in discover():
        cost = COST.get(sym, 0.5)
        for tf, horizon in TFS.items():
            p = f"{RAW}/{sym}_{tf}.parquet"
            if not os.path.exists(p):
                continue
            df = pd.read_parquet(p).sort_index()
            split_ts = df.index[int(len(df) * IS_FRACTION)]
            embargo = pd.Timedelta(hours=horizon * (1 if tf == "H1" else 4))

            reg, _, _ = detect_regime(df)
            base = (ema(df["close"], 20) > ema(df["close"], 50)) & (reg == "trend")
            base = base.astype(bool)
            entries = base & (~base.shift(1, fill_value=False))   # entry = signal turns ON

            feats = build_features(df, symbol=sym, tf=tf)
            labels = triple_barrier_labels(df, entries, horizon)
            model, test, auc = train_eval(feats, labels, split_ts, embargo, kind="hist")
            _, test_ens, auc_ens = train_eval(feats, labels, split_ts, embargo, kind="ensemble")

            n_active = sum(1 for c in feats.columns if feats[c].notna().any())
            print("=" * 92)
            print(f"  {sym} {tf}   entries={int(entries.sum())}   OOS entries={len(test)}   "
                  f"features active={n_active}/{len(feats.columns)}   "
                  f"AUC hist={auc:.3f} / ensemble={auc_ens:.3f}   cost=${cost}")
            print("=" * 92)
            print(f"    {'variant':<26}{'trades':>6}{'win%':>7}{'exp$':>9}{'PF':>7}"
                  f"{'total$':>10}{'maxDD$':>9}{'Sharpe':>8}")
            all_s = trade_stats(test["pnl"], cost, bpy[tf], horizon)
            show("ALL trend entries", all_s)
            if model is not None:
                sel = test[test["proba"] >= THRESHOLD]
                show(f"hist  P>= {THRESHOLD}", trade_stats(sel["pnl"], cost, bpy[tf], horizon))
                sel_e = test_ens[test_ens["proba"] >= THRESHOLD]
                show(f"ensemble  P>= {THRESHOLD}", trade_stats(sel_e["pnl"], cost, bpy[tf], horizon))
                # feature importance via permutation-free proxy: use model's training via
                # built-in is not available; report top features by simple correlation on test
                imp = (test[[c for c in feats.columns]].apply(
                    lambda col: np.corrcoef(col.fillna(col.median()), test["label"])[0, 1]
                    if col.notna().any() and col.std() > 0 else 0.0))
                top = imp.abs().sort_values(ascending=False).head(6)
                print("    top features (|corr| with win on OOS): " +
                      ", ".join(f"{k}={imp[k]:+.2f}" for k in top.index))
            print()


if __name__ == "__main__":
    run()
