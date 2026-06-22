# india/research/crash_model.py
"""
CRASH / DRAWDOWN-PROBABILITY MODEL (risk-first, López de Prado-style).
Target: will this stock suffer a >15% MAX DRAWDOWN over the next month? (crash=1)
Same 31 features, XGBoost, monthly walk-forward OOS (2024-26). Report AUC, then a portfolio test:
does AVOIDING the top-quintile predicted-crash names reduce drawdown vs holding everyone?

If crash is predictable AND avoiding it cuts drawdown -> graduate to Core as a blow-up filter.

Run: python india/research/crash_model.py
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
from sklearn.metrics import roc_auc_score

FEATS = feature_list("full")
H, THRESH = 21, -0.15


def forward_drawdown():
    closes = load_panels()[0]
    dret = closes.pct_change(); didx = closes.index
    rows = {}
    for d in didx[::H]:
        i = didx.get_loc(d); fut = dret.iloc[i + 1:i + 1 + H]
        if len(fut) < 5:
            continue
        cum = (1 + fut.fillna(0)).cumprod()
        rows[d] = (cum / cum.cummax() - 1).min()
    return pd.DataFrame(rows).T


def main():
    df = build_dataset("M").dropna(subset=["fwd_ret"]).copy()
    dd = forward_drawdown().stack(); dd.index.names = ["date", "symbol"]
    df = df.join(dd.rename("fdd")).dropna(subset=["fdd"])
    df["crash"] = (df["fdd"] < THRESH).astype(int)
    base = df["crash"].mean()
    print("=" * 60)
    print(f"  CRASH MODEL — P(next-month drawdown < {THRESH:.0%})   base rate {100*base:.0f}%")
    print("=" * 60)
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    oos = pd.Timestamp("2024-01-01"); preds = []
    for i, td in enumerate(dates):
        if td < oos or i == 0:
            continue
        tr = df[df.index.get_level_values("date").isin(dates[:i - 1])]
        if tr["crash"].nunique() < 2 or len(tr) < 500:
            continue
        m = xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.04, subsample=0.8,
                              colsample_bytree=0.8, reg_lambda=1.0, n_jobs=-1, eval_metric="logloss")
        m.fit(tr[FEATS].values, tr["crash"].values)
        te = df[df.index.get_level_values("date") == td]
        p = m.predict_proba(te[FEATS].values)[:, 1]
        preds.append(pd.DataFrame({"date": td, "symbol": te.index.get_level_values("symbol"),
                                   "p": p, "crash": te["crash"].values, "fwd_ret": te["fwd_ret"].values,
                                   "fdd": te["fdd"].values}))
    pred = pd.concat(preds, ignore_index=True)
    print(f"  AUC (crash predictable?): {roc_auc_score(pred['crash'], pred['p']):.3f}  (0.50=no skill)")

    # portfolio test: avoid top-quintile predicted-crash names each month
    avoid_dd, all_dd, avoid_r, all_r = [], [], [], []
    for _, g in pred.groupby("date"):
        cut = g["p"].quantile(0.80)
        keep = g[g["p"] < cut]
        avoid_dd.append(keep["fdd"].mean()); all_dd.append(g["fdd"].mean())
        avoid_r.append(keep["fwd_ret"].mean()); all_r.append(g["fwd_ret"].mean())
    print(f"\n  avg next-month drawdown:  AVOID-crash basket {100*np.mean(avoid_dd):+.2f}%   "
          f"hold-all {100*np.mean(all_dd):+.2f}%")
    print(f"  avg next-month return:    AVOID-crash basket {100*np.mean(avoid_r):+.2f}%   "
          f"hold-all {100*np.mean(all_r):+.2f}%")
    better = np.mean(avoid_dd) > np.mean(all_dd)
    print(f"\n  -> avoiding predicted-crash names {'REDUCES drawdown' if better else 'does NOT help'} "
          f"(graduate to Core blow-up filter: {'YES' if better else 'no'})")


if __name__ == "__main__":
    main()
