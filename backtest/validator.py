# backtest/validator.py
"""
The rigor gate. A strategy is only believable if it survives THIS, not a single
in-sample/out-of-sample split.

Provides:
  * walk_forward()        : roll a rules strategy across N contiguous time folds and
                            measure STABILITY (does the edge persist across periods,
                            not just one lucky window?).
  * cpcv_metalabel()      : Combinatorial Purged Cross-Validation (Lopez de Prado) for
                            the ML meta-labeler -> a DISTRIBUTION of out-of-sample paths
                            (AUC + selected-trade performance), with purging + embargo so
                            overlapping triple-barrier labels cannot leak.
  * probabilistic_sharpe_ratio() / deflated_sharpe_ratio() : is the Sharpe real once you
                            account for sample length, non-normality, and how MANY
                            strategies you tried (multiple-testing)?
"""
from itertools import combinations
import numpy as np
import pandas as pd
from scipy.stats import norm

from backtest.engine import backtest, stats, BARS_PER_YEAR


# ----------------------------------------------------------- walk-forward (rules)
def walk_forward(df, signal_fn, cost, tf, n_folds=6):
    """Evaluate a rules strategy on N contiguous OOS time folds. Returns per-fold
    stats + a stability summary. (Our strategies have fixed params, so the relevant
    robustness test is temporal persistence, not parameter re-fitting.)"""
    notional = df["close"].iloc[0]
    bounds = np.array_split(np.arange(len(df)), n_folds)
    rows = []
    for k, seg in enumerate(bounds):
        sd = df.iloc[seg[0]:seg[-1] + 1]
        s = stats(*backtest(sd, signal_fn(sd), cost), notional, tf)
        rows.append({"fold": k + 1, "from": sd.index[0].date(), "to": sd.index[-1].date(),
                     "trades": s["trades"] if s else 0,
                     "sharpe": s["sharpe"] if s else np.nan,
                     "total": s["total"] if s else 0.0,
                     "maxdd": s["dd"] if s else np.nan})
    res = pd.DataFrame(rows)
    sh = res["sharpe"].dropna()
    summary = {"folds": len(res), "mean_sharpe": sh.mean(), "std_sharpe": sh.std(),
               "pct_folds_positive": (res["total"] > 0).mean(),
               "worst_fold_sharpe": sh.min(), "best_fold_sharpe": sh.max()}
    return res, summary


# ----------------------------------------------------------- deflated / probabilistic Sharpe
def probabilistic_sharpe_ratio(sr, n_obs, skew=0.0, kurt=3.0, sr_benchmark=0.0):
    """P(true Sharpe > benchmark) given sample length and non-normality. sr/sr_b are
    per-observation (NOT annualised)."""
    if n_obs < 2:
        return np.nan
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2)
    return float(norm.cdf((sr - sr_benchmark) * np.sqrt(n_obs - 1) / max(denom, 1e-9)))


def probability_of_backtest_overfitting(returns_matrix, n_splits=10):
    """PBO via Combinatorially-Symmetric Cross-Validation (Bailey, Borwein, Lopez de
    Prado & Zhu 2017) — the research's explicit anti-overfitting test.

    returns_matrix: DataFrame [time x strategy] of per-bar returns for N candidate configs.
    Splits time into n_splits chunks; for every way to choose half as IS, picks the
    IS-best strategy and checks its OOS rank. PBO = P(the IS-best lands in the bottom
    half OOS) — i.e. probability the selection was overfit. <0.5 good, ->1 = pure overfit."""
    from itertools import combinations
    R = returns_matrix.dropna()
    if R.shape[1] < 2 or len(R) < n_splits * 4:
        return float("nan")
    chunks = np.array_split(np.arange(len(R)), n_splits)
    half = n_splits // 2
    logits = []
    for is_combo in combinations(range(n_splits), half):
        is_idx = np.concatenate([chunks[g] for g in is_combo])
        oos_idx = np.concatenate([chunks[g] for g in range(n_splits) if g not in is_combo])
        is_sr = R.iloc[is_idx].mean() / R.iloc[is_idx].std().replace(0, np.nan)
        oos_sr = R.iloc[oos_idx].mean() / R.iloc[oos_idx].std().replace(0, np.nan)
        best = is_sr.idxmax()
        rank = oos_sr.rank(pct=True)[best]              # OOS percentile of IS-best
        w = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(np.log(w / (1 - w)))
    logits = np.array(logits)
    return float((logits <= 0).mean())                  # fraction where IS-best is below OOS median


def deflated_sharpe_ratio(sr, n_obs, n_trials, sharpe_variance, skew=0.0, kurt=3.0):
    """Deflated Sharpe: PSR against the EXPECTED MAX Sharpe of n_trials independent
    random strategies. Guards against picking the best of many backtests."""
    if n_trials < 1 or sharpe_variance <= 0:
        return np.nan
    e = 0.5772156649  # Euler-Mascheroni
    z1 = norm.ppf(1 - 1.0 / n_trials)
    z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
    sr0 = np.sqrt(sharpe_variance) * ((1 - e) * z1 + e * z2)   # expected max under nulls
    return probabilistic_sharpe_ratio(sr, n_obs, skew, kurt, sr_benchmark=sr0)


# ----------------------------------------------------------- CPCV for the meta-labeler
def cpcv_metalabel(df, entries, horizon, build_features, triple_barrier_labels,
                   symbol, tf, n_groups=8, k_test=2, threshold=0.55):
    """Combinatorial Purged CV. Splits the labelled entries into n_groups contiguous
    blocks; for every choice of k_test test-blocks, trains on the rest (PURGING train
    entries whose label window overlaps a test block + EMBARGO of `horizon`), scores the
    test entries, and records (AUC, selected-trade per-trade mean PnL). Returns the
    DISTRIBUTION across all C(n_groups, k_test) paths."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    feats = build_features(df, symbol=symbol, tf=tf)
    labels = triple_barrier_labels(df, entries, horizon)
    data = labels.join(feats, how="left").dropna(subset=["label"])
    if len(data) < 60 or data["label"].nunique() < 2:
        return None
    X_cols = [c for c in feats.columns if data[c].nunique(dropna=True) >= 2]
    ts = data.index.values
    pos = np.arange(len(data))
    groups = np.array_split(pos, n_groups)
    emb = pd.Timedelta(hours=horizon * (1 if tf == "H1" else 4 if tf == "H4" else 24))
    lab_span = emb  # label window ~ horizon

    paths = []
    for test_combo in combinations(range(n_groups), k_test):
        test_idx = np.concatenate([groups[g] for g in test_combo])
        test_times = pd.DatetimeIndex(ts[test_idx])
        # purge: drop train rows whose [t, t+lab_span] overlaps any test window +/- embargo
        keep = []
        for j in pos:
            if j in set(test_idx):
                continue
            tj = pd.Timestamp(ts[j])
            overlap = ((test_times >= tj - emb) & (test_times <= tj + lab_span + emb)).any()
            if not overlap:
                keep.append(j)
        train_idx = np.array(keep, dtype=int)
        if len(train_idx) < 40 or data.iloc[train_idx]["label"].nunique() < 2:
            continue
        tr, te = data.iloc[train_idx], data.iloc[test_idx]
        m = HistGradientBoostingClassifier(max_iter=200, max_depth=4, learning_rate=0.05,
                                           l2_regularization=1.0, min_samples_leaf=20, random_state=0)
        m.fit(tr[X_cols], tr["label"])
        proba = m.predict_proba(te[X_cols])[:, 1]
        try:
            auc = roc_auc_score(te["label"], proba) if te["label"].nunique() > 1 else np.nan
        except ValueError:
            auc = np.nan
        sel = te["pnl"][proba >= threshold]
        paths.append({"auc": auc, "n_test": len(te), "n_selected": len(sel),
                      "sel_mean_pnl": sel.mean() if len(sel) else np.nan})
    if not paths:
        return None
    p = pd.DataFrame(paths)
    return {"n_paths": len(p), "auc_median": p["auc"].median(), "auc_iqr": p["auc"].quantile([.25, .75]).tolist(),
            "auc_pct_above_0.55": (p["auc"] > 0.55).mean(),
            "sel_pnl_median": p["sel_mean_pnl"].median(),
            "sel_pnl_pct_positive": (p["sel_mean_pnl"] > 0).mean(), "table": p}
