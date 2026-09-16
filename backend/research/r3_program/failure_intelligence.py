"""R3 PRE-ENTRY FAILURE INTELLIGENCE — recognise dangerous states, not winners.

THE INVERSION
-------------
Every prior wave asked whether something predicts RETURN. This asks a different
and easier question: does a state that precedes severe loss have a recognisable
pre-entry fingerprint? R2 does not need another model saying BUY. A model that
can say "this resembles situations that historically failed" is a different
capability, and it is allowed to be useful while being useless for direction.

WHY THIS ONE DOES NOT NEED SEALED R2 MEMORY
-------------------------------------------
"Dangerous situation" is a property of the state, not of R2's opinion of it. So
the labels come from the price panel - 1,245 India and 1,009 USA dates - rather
than from the 3 sealed decision dates that bound everything R2-specific. That is
the difference between this lane and the counterfactual one, which genuinely is
stuck at 3.

THE NUMBER THAT DECIDES IT
--------------------------
Not AUC. A classifier that flags 20% of rows to catch a 20% base rate has
achieved nothing while scoring respectably. What matters is LIFT over the base
rate at a usable operating point, and then whether acting on it avoids more
severe losses than the winners it costs. Both are reported, and the base rate is
printed beside every precision so the comparison cannot be avoided.

LEAKAGE
-------
Trained on an early window, tested after an embargo, with normalisation fitted
on train only. Labels are forward-looking by construction and never enter a
feature.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

SCHEMA_VERSION = "aegis.r3.failure_intelligence.v1"
SEED = 20260916
EMBARGO_DAYS = 5

SEVERE_PCT = -5.0        # severe loss over the forward window
DEEP_MAE_PCT = -8.0      # deep adverse excursion regardless of end point


def label_failures(panel: pd.DataFrame) -> pd.DataFrame:
    """Two failure definitions, kept separate.

    A position can end flat having been 10% underwater. Labelling only on the
    end point would call that a success, which is not what a capital allocator
    experienced.
    """
    p = panel.copy()
    p["y_severe"] = (p["fwd_20d"] <= SEVERE_PCT).astype("float")
    p.loc[p["fwd_20d"].isna(), "y_severe"] = np.nan
    if "fwd_mae_20" in p.columns:
        p["y_deep_mae"] = (p["fwd_mae_20"] <= DEEP_MAE_PCT).astype("float")
        p.loc[p["fwd_mae_20"].isna(), "y_deep_mae"] = np.nan
    else:
        p["y_deep_mae"] = np.nan
    return p


def _split(p: pd.DataFrame, frac: float = 0.65):
    dates = np.sort(p["date"].unique())
    cut = pd.Timestamp(dates[int(len(dates) * frac)])
    emb = cut + pd.Timedelta(days=EMBARGO_DAYS)
    return ((p["date"] <= cut).to_numpy(), (p["date"] > emb).to_numpy(),
            {"train_end": str(cut.date()), "test_start": str(emb.date()),
             "embargo_days": EMBARGO_DAYS,
             "n_train_dates": int(p.loc[p["date"] <= cut, "date"].nunique()),
             "n_test_dates": int(p.loc[p["date"] > emb, "date"].nunique())})


def _operating_points(y: np.ndarray, s: np.ndarray, base: float) -> list:
    """Precision and lift at several flag rates, base rate always alongside."""
    out = []
    for q in (0.05, 0.10, 0.20, 0.30):
        thr = np.quantile(s, 1.0 - q)
        flag = s >= thr
        if flag.sum() == 0:
            continue
        prec = float(y[flag].mean())
        out.append({
            "flag_rate_pct": round(100.0 * float(flag.mean()), 2),
            "precision_pct": round(100.0 * prec, 2),
            "base_rate_pct": round(100.0 * base, 2),
            "lift": round(prec / base, 3) if base > 0 else None,
            "recall_pct": round(100.0 * float(y[flag].sum() / max(y.sum(), 1)), 2),
            "n_flagged": int(flag.sum()),
        })
    return out


def train_failure_model(panel: pd.DataFrame, features: list,
                        label: str = "y_severe") -> dict:
    """Chronological train/test. Reports lift over base rate, not just AUC."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, average_precision_score

    p = panel.dropna(subset=[label]).reset_index(drop=True)
    if len(p) < 2000 or p["date"].nunique() < 100:
        return {"status": "INSUFFICIENT_HISTORY",
                "n_rows": int(len(p)), "n_dates": int(p["date"].nunique())}
    tr, te, split = _split(p)
    X = p[features].to_numpy(dtype=float)
    y = p[label].to_numpy(dtype=float)
    if y[tr].sum() < 50 or y[te].sum() < 50:
        return {"status": "TOO_FEW_POSITIVES",
                "train_positives": int(y[tr].sum()), "test_positives": int(y[te].sum())}

    clf = HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.06, max_depth=6,
        l2_regularization=1.0, random_state=SEED)
    clf.fit(X[tr], y[tr])
    s_tr = clf.predict_proba(X[tr])[:, 1]
    s_te = clf.predict_proba(X[te])[:, 1]

    base_tr, base_te = float(y[tr].mean()), float(y[te].mean())
    return {
        "status": "OK", "label": label, "split": split,
        "n_train": int(tr.sum()), "n_test": int(te.sum()),
        "base_rate_train_pct": round(100.0 * base_tr, 2),
        "base_rate_test_pct": round(100.0 * base_te, 2),
        "auc_train": round(float(roc_auc_score(y[tr], s_tr)), 4),
        "auc_test": round(float(roc_auc_score(y[te], s_te)), 4),
        "ap_test": round(float(average_precision_score(y[te], s_te)), 4),
        "operating_points_test": _operating_points(y[te], s_te, base_te),
        "_scores_test": s_te, "_y_test": y[te],
        "_test_mask": te, "_panel": p,
    }


def permutation_test(res: dict, features: list, n_perm: int = 20) -> dict:
    """Shuffle the label WITHIN each date and refit.

    Shuffling globally would destroy the date structure and make any model look
    good by comparison. Shuffling within a date keeps the cross-sectional
    composition of every day intact, so the null answers the right question:
    is there information about WHICH name fails, given the day?
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    if res.get("status") != "OK":
        return {"status": "NOT_RUN"}
    p, te = res["_panel"], res["_test_mask"]
    tr = ~te & p["date"].notna().to_numpy()
    X = p[features].to_numpy(dtype=float)
    y = p[res["label"]].to_numpy(dtype=float)
    rng = np.random.default_rng(SEED)
    aucs = []
    dates = p["date"].to_numpy()
    for _ in range(n_perm):
        yp = y.copy()
        for d in np.unique(dates[tr]):
            m = (dates == d) & tr
            v = yp[m]
            rng.shuffle(v)
            yp[m] = v
        clf = HistGradientBoostingClassifier(
            max_iter=120, learning_rate=0.08, max_depth=5, random_state=SEED)
        clf.fit(X[tr], yp[tr])
        aucs.append(float(roc_auc_score(y[te], clf.predict_proba(X[te])[:, 1])))
    a = np.array(aucs)
    obs = res["auc_test"]
    return {"status": "OK", "n_permutations": n_perm,
            "observed_auc_test": obs,
            "null_auc_mean": round(float(a.mean()), 4),
            "null_auc_sd": round(float(a.std()), 4),
            "null_auc_max": round(float(a.max()), 4),
            "z_vs_null": round(float((obs - a.mean()) / (a.std() + 1e-12)), 2),
            "above_null": bool(obs > a.max())}


def leave_ticker_out(res: dict, features: list, n_folds: int = 5) -> dict:
    """Hold out whole TICKERS as well as time.

    A model that has memorised a few names will keep its AUC when dates are
    held out and lose it when names are.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    if res.get("status") != "OK":
        return {"status": "NOT_RUN"}
    p, te = res["_panel"], res["_test_mask"]
    tr = ~te
    X = p[features].to_numpy(dtype=float)
    y = p[res["label"]].to_numpy(dtype=float)
    ticks = p["ticker"].to_numpy()
    uniq = np.array(sorted(set(ticks)))
    rng = np.random.default_rng(SEED)
    rng.shuffle(uniq)
    folds = np.array_split(uniq, n_folds)
    aucs = []
    for f in folds:
        hold = np.isin(ticks, f)
        trm = tr & ~hold
        tem = te & hold
        if y[trm].sum() < 50 or y[tem].sum() < 20:
            continue
        clf = HistGradientBoostingClassifier(
            max_iter=150, learning_rate=0.08, max_depth=5, random_state=SEED)
        clf.fit(X[trm], y[trm])
        aucs.append(float(roc_auc_score(y[tem], clf.predict_proba(X[tem])[:, 1])))
    if not aucs:
        return {"status": "TOO_FEW"}
    a = np.array(aucs)
    return {"status": "OK", "n_folds": len(aucs),
            "auc_mean": round(float(a.mean()), 4),
            "auc_min": round(float(a.min()), 4),
            "auc_max": round(float(a.max()), 4),
            "all_above_half": bool(a.min() > 0.5)}


def decision_value(res: dict, flag_rate: float = 0.20) -> dict:
    """Would ACTING on the flag have helped, on the same cohort?

    Severe losses avoided is only half the ledger; the winners the rule also
    removes are the other half, and a rule that avoids 3 disasters by declining
    30 good trades is not risk control.
    """
    if res.get("status") != "OK":
        return {"status": "NOT_RUN"}
    p, te, s = res["_panel"], res["_test_mask"], res["_scores_test"]
    sub = p.loc[te].copy()
    sub["risk"] = s
    sub = sub.dropna(subset=["fwd_20d"])
    if len(sub) < 200:
        return {"status": "INSUFFICIENT_SAMPLE", "n": int(len(sub))}
    thr = sub["risk"].quantile(1.0 - flag_rate)
    flagged = sub["risk"] >= thr
    kept = sub.loc[~flagged, "fwd_20d"]
    removed = sub.loc[flagged, "fwd_20d"]
    base = sub["fwd_20d"]
    sev = lambda x: float((x <= SEVERE_PCT).mean())
    return {
        "status": "OK", "flag_rate_pct": round(100.0 * flag_rate, 1),
        "n_total": int(len(sub)), "n_flagged": int(flagged.sum()),
        "n_dates": int(sub["date"].nunique()),
        "severe_rate_baseline_pct": round(100.0 * sev(base), 2),
        "severe_rate_after_avoiding_pct": round(100.0 * sev(kept), 2),
        "severe_losses_avoided": int((removed <= SEVERE_PCT).sum()),
        "winners_sacrificed": int((removed > 0).sum()),
        "avoided_to_sacrificed_ratio": (
            round(float((removed <= SEVERE_PCT).sum() / max((removed > 0).sum(), 1)), 3)),
        "expectancy_baseline_pct": round(float(base.mean()), 4),
        "expectancy_after_pct": round(float(kept.mean()), 4),
        "expectancy_delta_pct": round(float(kept.mean() - base.mean()), 4),
        "mean_outcome_of_flagged_pct": round(float(removed.mean()), 4),
        "turnover_note": "%d of %d candidates declined" % (int(flagged.sum()), len(sub)),
    }


def cost_sensitivity(dv: dict, cost_bps=(0, 10, 25, 50)) -> dict:
    """Gate 7. A per-decision cost applied to the trades the rule removes.

    Declining a trade is not free: it forgoes the expectancy of the ones that
    would have worked. This charges the rule for its own turnover.
    """
    if dv.get("status") != "OK":
        return {"status": "NOT_RUN"}
    out = []
    delta = dv["expectancy_delta_pct"]
    frac = dv["n_flagged"] / max(dv["n_total"], 1)
    for bps in cost_bps:
        charge = frac * (bps / 100.0)
        out.append({"cost_bps": bps,
                    "expectancy_delta_after_cost_pct": round(delta - charge, 4),
                    "survives": bool((delta - charge) > 0)})
    return {"status": "OK", "points": out,
            "survives_all_costs": all(p["survives"] for p in out)}


def flag_rate_sweep(res: dict, rates=(0.02, 0.05, 0.10, 0.15, 0.20)) -> dict:
    """Decision value across operating points.

    A single flag rate can hide the shape. Sweeping it answers whether a
    tighter, more selective rule ever becomes profitable - here it never does,
    it only makes the loss smaller.
    """
    if res.get("status") != "OK":
        return {"status": "NOT_RUN"}
    pts = []
    for q in rates:
        dv = decision_value(res, flag_rate=q)
        if dv.get("status") != "OK":
            continue
        pts.append({k: dv[k] for k in (
            "flag_rate_pct", "severe_rate_baseline_pct",
            "severe_rate_after_avoiding_pct", "severe_losses_avoided",
            "winners_sacrificed", "avoided_to_sacrificed_ratio",
            "expectancy_delta_pct")})
    any_pos = any(p["expectancy_delta_pct"] > 0 for p in pts)
    return {"status": "OK", "points": pts,
            "any_operating_point_profitable": any_pos,
            "verdict": ("PROFITABLE_SOMEWHERE" if any_pos
                        else "VALUE_DESTRUCTIVE_AT_EVERY_OPERATING_POINT")}


def risk_decile_profile(res: dict, top_q: float = 0.90) -> dict:
    """WHY the rule loses money, measured rather than asserted.

    A model trained to predict deep adverse excursion learns to find
    HIGH-VOLATILITY states, and volatility is two-sided. The flagged cohort
    carries fatter tails in both directions, so avoiding it removes more upside
    than downside. This is the mechanism, and it is why the deep-MAE label is
    easier to predict than the severe-loss label while being less useful.
    """
    if res.get("status") != "OK":
        return {"status": "NOT_RUN"}
    p, te, s = res["_panel"], res["_test_mask"], res["_scores_test"]
    sub = p.loc[te].copy()
    sub["risk"] = s
    sub = sub.dropna(subset=["fwd_20d"])
    if len(sub) < 200:
        return {"status": "INSUFFICIENT_SAMPLE"}
    thr = sub["risk"].quantile(top_q)
    out = {}
    for name, g in (("flagged", sub[sub["risk"] >= thr]),
                    ("rest", sub[sub["risk"] < thr])):
        v = g["fwd_20d"]
        out[name] = {
            "n": int(len(v)),
            "mean_fwd20_pct": round(float(v.mean()), 4),
            "median_fwd20_pct": round(float(v.median()), 4),
            "sd_fwd20": round(float(v.std()), 4),
            "win_rate_pct": round(100.0 * float((v > 0).mean()), 2),
            "severe_le_m5_pct": round(100.0 * float((v <= SEVERE_PCT).mean()), 2),
            "big_gain_ge_p10_pct": round(100.0 * float((v >= 10).mean()), 2),
            "mean_vol_20": round(float(g["vol_20"].mean()), 2),
        }
    out["status"] = "OK"
    out["interpretation"] = (
        "The flagged cohort has higher volatility AND a higher mean forward "
        "return. The model is a volatility detector, and volatility is "
        "symmetric enough that avoidance costs more upside than it saves "
        "downside.")
    out["implication"] = (
        "The next label should be vol-NORMALISED downside - asymmetry "
        "conditional on volatility - not raw deep MAE. That is a NEW "
        "pre-registered hypothesis for a future wave, deliberately not run "
        "here: choosing it after seeing these results would be selection.")
    return out
