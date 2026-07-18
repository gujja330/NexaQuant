"""Adaptive Rec v2.0 · signal models.

Every model is deterministic (fixed random_state, fixed iteration counts).
Interface: fit(X_train, y_train) -> None; predict_proba(X) -> np.ndarray.

Baseline: raw confidence pass-through (what v1.4 does today).
Candidate: HistGradientBoosting (best top-tail performance in exploration).
Alternate: Regularised LogReg (linear baseline for feature importance)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


RANDOM_STATE = 42


@dataclass
class SignalModel:
    name: str
    predict: Callable[[np.ndarray], np.ndarray]
    feature_importance: dict[str, float]
    params: dict


def fit_baseline(X_train: np.ndarray, y_train: np.ndarray,
                    feature_names: list[str], confidence_index: int) -> SignalModel:
    """Baseline: raw `confidence` column pass-through. Fitting is a no-op."""
    def _predict(X: np.ndarray) -> np.ndarray:
        return np.clip(X[:, confidence_index], 0.0, 1.0)
    return SignalModel(
        name="v1.4_baseline_raw_confidence",
        predict=_predict,
        feature_importance={feature_names[confidence_index]: 1.0},
        params={"method": "pass-through"},
    )


def fit_hgb(X_train: np.ndarray, y_train: np.ndarray,
              feature_names: list[str]) -> SignalModel:
    """HistGradientBoosting classifier. Deterministic with fixed random_state."""
    clf = HistGradientBoostingClassifier(
        random_state=RANDOM_STATE,
        max_iter=200,
        max_depth=None,
        learning_rate=0.1,
        min_samples_leaf=20,
    )
    clf.fit(X_train, y_train)

    # Permutation importance on the training set — deterministic under a
    # fixed random_state. Uses the model's own scoring (default = accuracy).
    perm = permutation_importance(clf, X_train, y_train,
                                       n_repeats=8, random_state=RANDOM_STATE,
                                       scoring="neg_brier_score")
    imp_raw = perm.importances_mean
    # Convert to non-negative + normalise so importances sum to 1
    imp_raw = np.clip(imp_raw, 0.0, None)
    total = imp_raw.sum()
    if total > 0:
        imp_norm = imp_raw / total
    else:
        imp_norm = np.full_like(imp_raw, 1.0 / len(imp_raw))
    importances = {name: float(v) for name, v in zip(feature_names, imp_norm)}

    def _predict(X: np.ndarray) -> np.ndarray:
        return clf.predict_proba(X)[:, 1]

    return SignalModel(
        name="hgb_v2.0",
        predict=_predict,
        feature_importance=importances,
        params={"max_iter": 200, "min_samples_leaf": 20, "learning_rate": 0.1,
                 "random_state": RANDOM_STATE},
    )


def fit_logreg(X_train: np.ndarray, y_train: np.ndarray,
                 feature_names: list[str]) -> SignalModel:
    """Regularised logistic regression. Used for linear feature importance."""
    # Manual scaling for LR (HGB doesn't need it)
    sc = StandardScaler()
    X_scaled = sc.fit_transform(X_train)
    clf = LogisticRegression(max_iter=2000, C=0.3, random_state=RANDOM_STATE)
    clf.fit(X_scaled, y_train)

    # Absolute coefficient = importance
    coefs = np.abs(clf.coef_[0])
    total = coefs.sum() or 1.0
    importances = {name: float(c / total) for name, c in zip(feature_names, coefs)}

    def _predict(X: np.ndarray) -> np.ndarray:
        X_s = sc.transform(X)
        return clf.predict_proba(X_s)[:, 1]

    return SignalModel(
        name="logreg_v2.0",
        predict=_predict,
        feature_importance=importances,
        params={"C": 0.3, "max_iter": 2000, "random_state": RANDOM_STATE},
    )


def fit_all(X_train: np.ndarray, y_train: np.ndarray, feature_names: list[str],
              confidence_index: int) -> dict[str, SignalModel]:
    return {
        "v1.4_baseline_raw_confidence": fit_baseline(X_train, y_train, feature_names, confidence_index),
        "hgb_v2.0":                     fit_hgb(X_train, y_train, feature_names),
        "logreg_v2.0":                  fit_logreg(X_train, y_train, feature_names),
    }
