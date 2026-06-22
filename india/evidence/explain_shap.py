# india/research/explain_shap.py
"""
EXPLAINABILITY (SHAP) — WHY does the model forecast a stock as risky/calm?
Trains XGBoost to predict next-month VOLATILITY (the validated signal, AUC 0.76) and uses
XGBoost's NATIVE SHAP (pred_contribs — no extra package) to rank what drives the forecast.

This is the honest 'reason' behind each stock's weight: the bot weights by predictable RISK,
so SHAP shows which features make a stock predictably calm or volatile.

Run: python india/research/explain_shap.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from india.feature_engine import load_panels
import xgboost as xgb

FEATS = feature_list("full"); H = 21


def fwd_vol():
    closes = load_panels()[0]; dret = closes.pct_change(); didx = closes.index
    rows = {}
    for d in didx[::H]:
        i = didx.get_loc(d); fut = dret.iloc[i + 1:i + 1 + H]
        if len(fut) >= 5:
            rows[d] = fut.std() * np.sqrt(252)
    return pd.DataFrame(rows).T


if __name__ == "__main__":
    print("=" * 60)
    print("  SHAP — what drives the RISK (volatility) forecast?")
    print("=" * 60)
    df = build_dataset("M").copy()
    v = fwd_vol().stack(); v.index.names = ["date", "symbol"]
    df = df.join(v.rename("fvol")).dropna(subset=["fvol"])
    X, y = df[FEATS], df["fvol"]
    m = xgb.XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.04, subsample=0.8,
                         colsample_bytree=0.8, n_jobs=-1)
    m.fit(X.values, y.values)
    dm = xgb.DMatrix(X.values, feature_names=FEATS)
    contribs = m.get_booster().predict(dm, pred_contribs=True)[:, :-1]   # drop bias term
    imp = pd.Series(np.abs(contribs).mean(axis=0), index=FEATS).sort_values(ascending=False)
    print("\n  Top drivers of predicted risk (mean |SHAP|):")
    for f, val in imp.head(12).items():
        bar = "#" * int(40 * val / imp.max())
        print(f"   {f:<15}{bar} {val:.4f}")
    print("\n  -> these features explain WHY a stock is forecast calm vs volatile,")
    print("     and therefore why it gets more or less weight in the basket.")
