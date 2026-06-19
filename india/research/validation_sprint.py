# india/research/validation_sprint.py
"""
VALIDATION SPRINT — test the UNTESTED framings before concluding returns are unpredictable.
Honors the rule: let evidence decide. Walk-forward OOS (2024-26), all on the same 31 features.

  TEST 1  RANKING   — XGBRanker (LambdaMART/NDCG): rank IC vs actual return + top-15 basket
  TEST 2  PER-HORIZON PROBABILITY — P(>10% in 1m), P(>15% in 3m), P(>25% in 6m): AUC
  TEST 3  TRIPLE-BARRIER — P(hit +8% before -5% within 21d): AUC

Verdict per test: AUC/IC > ~0.55 OOS = real per-stock signal (output can show confidence);
~0.50 = unpredictable (output stays basket-level + risk-based).

Run: python india/research/validation_sprint.py
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
OOS = pd.Timestamp("2024-01-01")


def base():
    df = build_dataset("M").dropna(subset=["fwd_ret"]).copy()
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    return df, dates


# ---------- TEST 1: ranking ----------
def test_ranking(df, dates):
    dd = df.copy()
    dd["grade"] = dd.groupby(level="date")["fwd_ret"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 10, labels=False, duplicates="drop")).fillna(0).astype(int)
    ics, top = [], []
    model, last = None, -99
    for i, td in enumerate(dates):
        if td < OOS or i == 0:
            continue
        if model is None or i - last >= 3:
            tr = dd[dd.index.get_level_values("date").isin(dates[:i - 1])].sort_index(level="date")
            grp = tr.groupby(level="date").size().values
            model = xgb.XGBRanker(objective="rank:ndcg", n_estimators=250, max_depth=3,
                                  learning_rate=0.04, subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
            model.fit(tr[FEATS].values, tr["grade"].values, group=grp); last = i
        te = dd[dd.index.get_level_values("date") == td]
        p = model.predict(te[FEATS].values)
        ics.append(pd.Series(p).corr(pd.Series(te["fwd_ret"].values), method="spearman"))
        k = min(15, len(te)); idx = np.argsort(p)[-k:]
        top.append(te["fwd_ret"].values[idx].mean())
    eq = float((1 + pd.Series(top)).prod()); yrs = len(top) * 21 / 252
    return np.nanmean(ics), 100 * (eq ** (1 / yrs) - 1)


# ---------- TEST 2: per-horizon probability ----------
def fwd_ret(closes, H):
    return (closes.shift(-H) / closes - 1)


def test_horizon(df, dates):
    closes = load_panels()[0]
    res = {}
    for H, thr, label in [(21, 0.10, "1m >10%"), (63, 0.15, "3m >15%"), (126, 0.25, "6m >25%")]:
        fr = fwd_ret(closes, H)
        mdates = closes.index[::21]
        y = (fr.reindex(mdates).stack() > thr).astype(int)
        y.index.names = ["date", "symbol"]
        d = df.join(y.rename("y")).dropna(subset=["y"])
        if d["y"].nunique() < 2 or d["y"].mean() < 0.02:
            res[label] = (np.nan, d["y"].mean()); continue
        preds, ys, model, last = [], [], None, -99
        dts = np.array(sorted(d.index.get_level_values("date").unique()))
        for i, td in enumerate(dts):
            if td < OOS or i == 0:
                continue
            if model is None or i - last >= 3:
                tr = d[d.index.get_level_values("date").isin(dts[:i - 1])]
                if tr["y"].nunique() < 2 or len(tr) < 400:
                    continue
                model = xgb.XGBClassifier(n_estimators=250, max_depth=3, learning_rate=0.04,
                                          subsample=0.8, colsample_bytree=0.8, n_jobs=-1, eval_metric="logloss")
                model.fit(tr[FEATS].values, tr["y"].values); last = i
            if model is None:
                continue
            te = d[d.index.get_level_values("date") == td]
            preds += list(model.predict_proba(te[FEATS].values)[:, 1]); ys += list(te["y"].values)
        res[label] = (roc_auc_score(ys, preds) if len(set(ys)) > 1 else np.nan, np.mean(ys))
    return res


# ---------- TEST 3: triple-barrier ----------
def test_triple_barrier(df, dates):
    closes = load_panels()[0]; H, up, dn = 21, 0.08, -0.05
    mdates = closes.index[::21]; lab = {}
    for d0 in mdates:
        i = closes.index.get_loc(d0)
        win = closes.iloc[i + 1:i + 1 + H]
        if len(win) < 5:
            continue
        for s in closes.columns:
            p0 = closes.iloc[i][s]
            if not np.isfinite(p0):
                continue
            path = win[s] / p0 - 1
            hit_up = path[path >= up].index.min() if (path >= up).any() else None
            hit_dn = path[path <= dn].index.min() if (path <= dn).any() else None
            if hit_up is not None and (hit_dn is None or hit_up <= hit_dn):
                lab[(d0, s)] = 1
            elif hit_dn is not None:
                lab[(d0, s)] = 0
    y = pd.Series(lab); y.index.names = ["date", "symbol"]
    d = df.join(y.rename("y")).dropna(subset=["y"])
    dts = np.array(sorted(d.index.get_level_values("date").unique()))
    preds, ys, model, last = [], [], None, -99
    for i, td in enumerate(dts):
        if td < OOS or i == 0:
            continue
        if model is None or i - last >= 3:
            tr = d[d.index.get_level_values("date").isin(dts[:i - 1])]
            if tr["y"].nunique() < 2 or len(tr) < 400:
                continue
            model = xgb.XGBClassifier(n_estimators=250, max_depth=3, learning_rate=0.04,
                                      subsample=0.8, colsample_bytree=0.8, n_jobs=-1, eval_metric="logloss")
            model.fit(tr[FEATS].values, tr["y"].values); last = i
        if model is None:
            continue
        te = d[d.index.get_level_values("date") == td]
        preds += list(model.predict_proba(te[FEATS].values)[:, 1]); ys += list(te["y"].values)
    return (roc_auc_score(ys, preds) if len(set(ys)) > 1 else np.nan), np.mean(ys)


if __name__ == "__main__":
    print("=" * 64)
    print("  VALIDATION SPRINT — is per-stock return predictable in ANY framing?")
    print("  (OOS 2024-26; >0.55 = real signal, ~0.50 = unpredictable)")
    print("=" * 64)
    df, dates = base()
    ic, cagr = test_ranking(df, dates)
    print(f"\n  1) RANKING (XGBRanker)   rank-IC {ic:+.3f}   top-15 CAGR {cagr:.1f}%  (Nifty ~10.8%)")
    print("\n  2) PER-HORIZON PROBABILITY:")
    for k, (auc, base_rate) in test_horizon(df, dates).items():
        print(f"     P({k:<8})  AUC {auc:.3f}   (base rate {100*base_rate:.0f}%)")
    auc, br = test_triple_barrier(df, dates)
    print(f"\n  3) TRIPLE-BARRIER (+8% before -5%, 21d)   AUC {auc:.3f}   (win base {100*br:.0f}%)")
    print("\n  Verdict: if all ~0.50, per-stock return is unpredictable -> output stays basket-level.")
