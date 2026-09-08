"""ML DISCOVERY v1 · MODELS · CEO 2026-09-08.

LightGBM and XGBoost only. No SHAP dependency: it is not installed, and
the CEO was explicit that it must not be a prerequisite. It plugs in later
as an explanatory layer.

Targets, per the directive:
  regression      forward return
  classification  winner / loser
  severe loss     bottom decile of the cross-section

Deliberately small, heavily regularised trees. On a cohort this thin a
deep forest would memorise tickers and report it as skill; the point of
this layer is to rank features honestly, not to maximise a fit statistic.
"""
from __future__ import annotations

import math
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.models.v1"

TARGET_RETURN = "return"
TARGET_WINNER = "winner"
TARGET_SEVERE_LOSS = "severe_loss"

# Conservative on purpose · see module docstring.
LGB_PARAMS = {
    "objective": "regression", "num_leaves": 7, "max_depth": 3,
    "learning_rate": 0.05, "n_estimators": 200, "min_child_samples": 20,
    "subsample": 0.8, "colsample_bytree": 0.8, "reg_lambda": 1.0,
    "verbose": -1, "random_state": 20260908,
}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def build_matrix(rows: list, features: list, target: str, horizon: str):
    """Return (X, y, kept_feature_names, kept_row_index).

    Rows missing the TARGET are dropped. Rows missing a feature keep NaN -
    LightGBM handles it natively, and imputing would invent data the
    manifest just spent effort excluding.
    """
    import numpy as np
    from backend.research.ml_discovery.manifest import derive

    idx, ys, xs = [], [], []
    rets = [_num(r.get(horizon)) for r in rows]
    valid = [v for v in rets if v is not None]
    if not valid:
        return None, None, [], []
    cut = sorted(valid)[max(0, int(len(valid) * 0.10) - 1)]

    for i, r in enumerate(rows):
        y = _num(r.get(horizon))
        if y is None:
            continue
        if target == TARGET_RETURN:
            t = y
        elif target == TARGET_WINNER:
            t = 1.0 if y > 0 else 0.0
        else:
            t = 1.0 if y <= cut else 0.0
        d = derive(r)
        vals = []
        for f in features:
            v = d.get(f) if f in d else r.get(f)
            if isinstance(v, str):
                v = None
            vals.append(_num(v) if v is not None else float("nan"))
        idx.append(i)
        ys.append(t)
        xs.append(vals)

    X = np.array(xs, dtype=float)
    y = np.array(ys, dtype=float)
    # Drop columns that are entirely missing · a feature with no values
    # cannot be ranked and would silently occupy a slot.
    keep = [j for j in range(X.shape[1]) if not np.all(np.isnan(X[:, j]))]
    return X[:, keep], y, [features[j] for j in keep], idx


def fit(X, y, target: str):
    import lightgbm as lgb
    p = dict(LGB_PARAMS)
    if target in (TARGET_WINNER, TARGET_SEVERE_LOSS):
        p["objective"] = "binary"
        m = lgb.LGBMClassifier(**p)
    else:
        m = lgb.LGBMRegressor(**p)
    m.fit(X, y)
    return m


def score(model, X, y, target: str) -> dict:
    import numpy as np
    if target == TARGET_RETURN:
        pred = model.predict(X)
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        return {"metric": "r2",
                "value": round(1 - ss_res / ss_tot, 4) if ss_tot else None}
    proba = model.predict_proba(X)[:, 1]
    pos, neg = y == 1, y == 0
    if pos.sum() == 0 or neg.sum() == 0:
        return {"metric": "auc", "value": None}
    # Rank-based AUC · no sklearn import needed for a two-line calculation.
    order = np.argsort(proba)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(proba) + 1)
    auc = ((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2)
           / (pos.sum() * neg.sum()))
    return {"metric": "auc", "value": round(float(auc), 4)}
