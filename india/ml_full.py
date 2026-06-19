# india/ml_full.py
"""
FULL ML bench — XGBoost + LightGBM + HistGBM + RandomForest + ExtraTrees + Logistic + KNN + NB,
monthly expanding walk-forward (train->Dec-2023, predict Jan-2024, roll to 2026), all features,
every stock. Plus FEATURE IMPORTANCE (XGBoost gain + permutation importance, out-of-sample).

Target: will the stock BEAT the median stock next month? (balanced 50/50). AUC 0.50 = no skill.

Run: python india/ml_full.py
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
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import (HistGradientBoostingClassifier, RandomForestClassifier,
                              ExtraTreesClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (roc_auc_score, accuracy_score, precision_score,
                             recall_score, f1_score)
from sklearn.inspection import permutation_importance

FEATS = feature_list("full")


def models():
    imp = lambda m: make_pipeline(SimpleImputer(strategy="median"), m)
    impscale = lambda m: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), m)
    return {
        "XGBoost": xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.04,
                    subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, n_jobs=-1,
                    eval_metric="logloss", verbosity=0),
        "LightGBM": lgb.LGBMClassifier(n_estimators=300, max_depth=3, num_leaves=15,
                    learning_rate=0.04, subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
                    n_jobs=-1, verbose=-1),
        "HistGBM": HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.04,
                    l2_regularization=1.0, min_samples_leaf=60, random_state=0),
        "RandomForest": imp(RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=50,
                    n_jobs=-1, random_state=0)),
        "ExtraTrees": imp(ExtraTreesClassifier(n_estimators=300, max_depth=8, min_samples_leaf=40,
                    n_jobs=-1, random_state=0)),
        "Logistic": impscale(LogisticRegression(max_iter=1000, C=0.5)),
        "KNN": impscale(KNeighborsClassifier(n_neighbors=75)),
        "NaiveBayes": imp(GaussianNB()),
    }


def walkforward(oos_start="2024-01-01", embargo=1):
    df = build_dataset("M").dropna(subset=["fwd_ret"]).copy()
    df["y"] = (df["fwd_ret"] > df.groupby(level="date")["fwd_ret"].transform("median")).astype(int)
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    oos = pd.Timestamp(oos_start)
    names = list(models().keys())
    out = []
    for i, td in enumerate(dates):
        if td < oos or i == 0:
            continue
        tr = df[df.index.get_level_values("date").isin(dates[: i - embargo])]
        if tr["y"].nunique() < 2 or len(tr) < 500:
            continue
        Xtr, ytr = tr[FEATS].values, tr["y"].values
        fitted = {n: m.fit(Xtr, ytr) for n, m in models().items()}
        te = df[df.index.get_level_values("date") == td]
        rec = {"date": td, "symbol": te.index.get_level_values("symbol"),
               "fwd_ret": te["fwd_ret"].values, "y": te["y"].values}
        for n, m in fitted.items():
            rec[n] = m.predict_proba(te[FEATS].values)[:, 1]
        d = pd.DataFrame(rec); d["ENSEMBLE"] = d[names].mean(axis=1)
        out.append(d)
    return pd.concat(out, ignore_index=True), names


def port_cagr(pred, col, topn=10):
    rets = [g.nlargest(topn, col)["fwd_ret"].mean() - COST_BPS / 1e4 for _, g in pred.groupby("date")]
    s = pd.Series(rets); eq = float((1 + s).prod()); yrs = len(s) * 21 / 252
    return 100 * (eq ** (1 / max(yrs, .1)) - 1), s.mean() / (s.std() + 1e-12) * np.sqrt(12)


def feature_importance(oos_start="2024-01-01"):
    df = build_dataset("M").dropna(subset=["fwd_ret"]).copy()
    df["y"] = (df["fwd_ret"] > df.groupby(level="date")["fwd_ret"].transform("median")).astype(int)
    tr = df[df.index.get_level_values("date") < pd.Timestamp(oos_start)]
    te = df[df.index.get_level_values("date") >= pd.Timestamp(oos_start)]
    m = xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.04, subsample=0.8,
                          colsample_bytree=0.8, reg_lambda=1.0, n_jobs=-1, eval_metric="logloss")
    m.fit(tr[FEATS].values, tr["y"].values)
    gain = pd.Series(m.feature_importances_, index=FEATS).sort_values(ascending=False)
    perm = permutation_importance(m, te[FEATS].fillna(te[FEATS].median()).values, te["y"].values,
                                  n_repeats=5, random_state=0, scoring="roc_auc")
    permimp = pd.Series(perm.importances_mean, index=FEATS).sort_values(ascending=False)
    return gain, permimp


if __name__ == "__main__":
    print("=" * 84)
    print("  FULL ML BENCH — 8 models, monthly walk-forward (train->Dec23, roll to 2026)")
    print("=" * 84)
    nf = load_panels()[4]; neq = (1 + nf.pct_change().fillna(0)).cumprod()
    pred, names = walkforward()
    y = pred["y"].values
    print(f"  OOS {pred['date'].min().date()} -> {pred['date'].max().date()}  ({pred['date'].nunique()} months)")
    print("  CLASSIFICATION SCORES (predict 'beat median'; 0.50 AUC / 50% acc = coin flip):")
    print(f"  {'MODEL':<14}{'AUC':>7}{'Acc%':>7}{'Prec%':>7}{'Recall%':>8}{'F1':>6}{'  ||':>4}{'top10 CAGR':>12}{'Sharpe':>8}")
    print("  " + "-" * 76)
    for n in names + ["ENSEMBLE"]:
        auc = roc_auc_score(y, pred[n])
        yhat = (pred[n].values >= 0.5).astype(int)
        acc, prec = accuracy_score(y, yhat), precision_score(y, yhat, zero_division=0)
        rec, f1 = recall_score(y, yhat, zero_division=0), f1_score(y, yhat, zero_division=0)
        cagr, sh = port_cagr(pred, n)
        print(f"  {n:<14}{auc:>7.3f}{100*acc:>7.1f}{100*prec:>7.1f}{100*rec:>8.1f}{f1:>6.2f}{'  ||':>4}{cagr:>11.1f}%{sh:>8.2f}")
    print(f"  {'NIFTY':<14}{'':>7}{'':>7}{'':>7}{'':>8}{'':>6}{'  ||':>4}{10.7:>11.1f}%{0.80:>8.2f}")

    print("\n  FEATURE IMPORTANCE (which features carry signal?):")
    gain, permimp = feature_importance()
    print("   XGBoost gain (top 12):")
    for f, v in gain.head(12).items():
        print(f"      {f:<16}{v:.3f}")
    print("   Permutation importance OOS (top 8; ~0 means the feature adds no real predictive power):")
    for f, v in permimp.head(8).items():
        print(f"      {f:<16}{v:+.4f}")
