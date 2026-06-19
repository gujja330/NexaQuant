# india/target_test.py
"""
THE TARGET TEST (user's key insight): 'predicting next-month return is the wrong problem.'

Same features, same XGBoost, walk-forward OOS (train->Dec-2023, test 2024-2026). Only the TARGET
changes. We test which is actually PREDICTABLE (AUC well above 0.50):
  1. RETURN      : beat median forward return        (the usual target)
  2. LOW-VOL     : below-median forward volatility    (is risk predictable?)
  3. SMALL-DD    : smaller-than-median forward drawdown
  4. SHARPE      : above-median forward return/vol

Market lore: returns ~unpredictable, RISK persistent/predictable. If LOW-VOL/SMALL-DD score high
AUC while RETURN ~0.50, the lever is RISK prediction -> portfolio construction, not stock picking.

Run: python india/target_test.py
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
import xgboost as xgb
from sklearn.metrics import roc_auc_score

FEATS = feature_list("full")
H = 21      # forward horizon (1 month of trading days)


def forward_risk():
    """Per monthly date x stock: forward H-day volatility and max drawdown."""
    closes = load_panels()[0]
    dret = closes.pct_change()
    didx = closes.index
    monthly = didx[::H]
    vol_rows, dd_rows = {}, {}
    for d in monthly:
        i = didx.get_loc(d)
        fut = dret.iloc[i + 1: i + 1 + H]
        if len(fut) < 5:
            continue
        vol_rows[d] = fut.std() * np.sqrt(252)
        cum = (1 + fut.fillna(0)).cumprod()
        dd_rows[d] = (cum / cum.cummax() - 1).min()          # most-negative drawdown (<=0)
    vol = pd.DataFrame(vol_rows).T
    dd = pd.DataFrame(dd_rows).T
    return vol, dd


def targets(df):
    vol, dd = forward_risk()
    v = vol.stack(); d = dd.stack()
    v.index.names = d.index.names = ["date", "symbol"]
    df = df.join(v.rename("fvol")).join(d.rename("fdd"))
    by = df.groupby(level="date")
    out = pd.DataFrame(index=df.index)
    out["RETURN"] = (df["fwd_ret"] > by["fwd_ret"].transform("median")).astype(float)
    out["LOW_VOL"] = (df["fvol"] < by["fvol"].transform("median")).astype(float)
    out["SMALL_DD"] = (df["fdd"] > by["fdd"].transform("median")).astype(float)   # less negative
    sharpe = df["fwd_ret"] / (df["fvol"] + 1e-9)
    out["SHARPE"] = (sharpe > sharpe.groupby(level="date").transform("median")).astype(float)
    return df, out


def auc_for(df, y, oos="2024-01-01"):
    X = df[FEATS]
    mask = df.index.get_level_values("date") < pd.Timestamp(oos)
    keep = y.notna() & X.notna().any(axis=1)
    tr = mask & keep; te = (~mask) & keep
    m = xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.04, subsample=0.8,
                          colsample_bytree=0.8, reg_lambda=1.0, n_jobs=-1, eval_metric="logloss")
    m.fit(X[tr].values, y[tr].values)
    p = m.predict_proba(X[te].values)[:, 1]
    return roc_auc_score(y[te].values, p)


if __name__ == "__main__":
    print("=" * 60)
    print("  TARGET TEST — same XGBoost, different targets (OOS 2024-26)")
    print("  AUC 0.50 = coin flip; >0.60 = genuinely predictable")
    print("=" * 60)
    df = build_dataset("M").dropna(subset=["fwd_ret"]).copy()
    df, ys = targets(df)
    print(f"  {'TARGET':<12}{'AUC':>8}   predictable?")
    for col in ["RETURN", "LOW_VOL", "SMALL_DD", "SHARPE"]:
        a = auc_for(df, ys[col])
        tag = "YES - usable" if a > 0.60 else ("weak" if a > 0.55 else "NO (coin flip)")
        print(f"  {col:<12}{a:>8.3f}   {tag}")
    print("\n  If RISK targets (LOW_VOL/SMALL_DD) >> RETURN, the edge is risk prediction +")
    print("  portfolio construction (risk-parity/low-vol tilt), NOT picking winners.")
