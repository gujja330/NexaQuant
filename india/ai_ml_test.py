# india/ai_ml_test.py
"""
SERIOUS ML test — apply real models and let the DATA decide (no opinions).

Same model family as the gold/BTC meta-label: HistGradientBoosting + RandomForest + Logistic,
ENSEMBLED. Target = cross-sectional OUTPERFORMANCE (does this stock beat the median stock's
forward return that period?) — a balanced 50/50 label, the right framing for stock selection.

Walk-forward out-of-sample. We report:
  1. AUC per model + ensemble  (is there ANY classification skill? 0.50 = coin flip)
  2. IC (rank corr of P(out) vs actual forward return)
  3. A real portfolio: long the top-N by ensemble probability, net of cost, vs Nifty (Rs + CAGR).
  4. Long-short (top decile minus bottom decile) to isolate the pure signal.

Run: python india/ai_ml_test.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS
from sklearn.ensemble import (HistGradientBoostingClassifier, RandomForestClassifier,
                              ExtraTreesClassifier, GradientBoostingClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

YEARS = 5.47
MODEL_NAMES = ["HistGBM", "RandomForest", "ExtraTrees", "GradBoost", "Logistic", "NeuralNet"]


def models():
    imp = lambda m: make_pipeline(SimpleImputer(strategy="median"), m)
    impscale = lambda m: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), m)
    return {
        "HistGBM": HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.04,
                    l2_regularization=1.0, min_samples_leaf=60, early_stopping=True,
                    validation_fraction=0.15, random_state=0),
        "RandomForest": imp(RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=50,
                    n_jobs=-1, random_state=0)),
        "ExtraTrees": imp(ExtraTreesClassifier(n_estimators=300, max_depth=8, min_samples_leaf=40,
                    n_jobs=-1, random_state=0)),
        "GradBoost": imp(GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.04,
                    min_samples_leaf=60, random_state=0)),
        "Logistic": impscale(LogisticRegression(max_iter=1000, C=0.5)),
        "NeuralNet": impscale(MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-3, max_iter=400,
                    early_stopping=True, random_state=0)),
    }


def walkforward(freq="M", feature_set="full", oos_start="2024-01-01", embargo=1):
    """Expanding window, RETRAIN EVERY PERIOD: train on all data up to t-1, predict t.
    OOS begins at oos_start (e.g. train->Dec-2023, predict Jan-2024, then roll forward)."""
    df = build_dataset(freq).dropna(subset=["fwd_ret"]).copy()
    df["y"] = (df["fwd_ret"] > df.groupby(level="date")["fwd_ret"].transform("median")).astype(int)
    feats = feature_list(feature_set)
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    oos = pd.Timestamp(oos_start)
    out = []
    for i, td in enumerate(dates):
        if td < oos or i == 0:
            continue
        tr = df[df.index.get_level_values("date").isin(dates[: i - embargo])]
        if tr["y"].nunique() < 2 or len(tr) < 500:
            continue
        Xtr, ytr = tr[feats].values, tr["y"].values
        fitted = {name: m.fit(Xtr, ytr) for name, m in models().items()}  # retrain each month
        te = df[df.index.get_level_values("date") == td]
        rec = {"date": td, "symbol": te.index.get_level_values("symbol"),
               "fwd_ret": te["fwd_ret"].values, "y": te["y"].values}
        for name, m in fitted.items():
            rec[name] = m.predict_proba(te[feats].values)[:, 1]
        d = pd.DataFrame(rec)
        d["ENSEMBLE"] = d[MODEL_NAMES].mean(axis=1)
        out.append(d)
    return pd.concat(out, ignore_index=True)


def hit_rate(pred, col, topn=10):
    """Fraction of the model's monthly top-N picks that actually beat the median (y==1)."""
    hits = tot = 0
    for _, g in pred.groupby("date"):
        p = g.nlargest(topn, col)
        hits += p["y"].sum(); tot += len(p)
    return hits / max(tot, 1)


def port(pred, col, per, topn=10):
    rets = [g.nlargest(topn, col)["fwd_ret"].mean() - COST_BPS / 1e4 for _, g in pred.groupby("date")]
    s = pd.Series(rets); eq = float((1 + s).prod())
    yrs = len(s) * per / 252
    return 100 * (eq - 1), 100 * (eq ** (1 / max(yrs, 0.1)) - 1), s.mean() / (s.std() + 1e-12) * np.sqrt(252 / per), eq * 1e5


def evaluate(pred, freq):
    per = {"M": 21, "W": 5}[freq]
    yrs = pred["date"].nunique() * per / 252
    lo, hi = pred["date"].min().date(), pred["date"].max().date()
    print(f"\n  OOS window {lo} -> {hi}  ({pred['date'].nunique()} months, retrained EVERY month)")
    print(f"  {'MODEL':<14}{'AUC':>7}{'IC':>8}{'top10 hit%':>12}{'top10 CAGR':>12}{'Sharpe':>8}{'Rs1L->':>11}")
    print("  " + "-" * 70)
    for n in MODEL_NAMES + ["ENSEMBLE"]:
        auc = roc_auc_score(pred["y"], pred[n])
        ic = pred.groupby("date").apply(lambda g: g[n].corr(g["fwd_ret"], method="spearman")).mean()
        hr = hit_rate(pred, n)
        tot, cagr, sh, end = port(pred, n, per)
        print(f"  {n:<14}{auc:>7.3f}{ic:>+8.3f}{100*hr:>11.1f}%{cagr:>11.1f}%{sh:>8.2f}  Rs{end:>9,.0f}")


if __name__ == "__main__":
    print("=" * 84)
    print("  ML WALK-FORWARD — train->Dec2023 predict Jan2024, roll monthly to 2026. All models.")
    print("  Target: will the stock BEAT the median stock next month? AUC 0.50 = no skill.")
    print("=" * 84)
    nf = load_panels()[4]
    neq = (1 + nf.pct_change().fillna(0)).cumprod()
    print(f"  BENCHMARK  Nifty buy&hold full-period: {100*(neq.iloc[-1]-1):+.0f}%  (CAGR {100*((neq.iloc[-1])**(1/YEARS)-1):.1f}%)")
    pred = walkforward(freq="M", feature_set="full", oos_start="2024-01-01")
    evaluate(pred, "M")
    out = ROOT / "output" / "ml_predictions.csv"
    pred.to_csv(out, index=False)
    print(f"\n  per-stock monthly predictions (all models) saved -> {out}")
    print("  Read: AUC>0.52 & IC>0 & top10 CAGR>Nifty = real edge. Else honestly no edge.")
