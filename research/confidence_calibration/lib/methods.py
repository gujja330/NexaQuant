"""DEV029 calibration methods — 5 institutional approaches.

Each calibrator takes (raw_confidences, outcomes) → returns a fitted
transformer with .predict() that maps raw confidence → calibrated probability.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np


EPS = 1e-6


def _clamp01(x):
    return np.clip(x, EPS, 1 - EPS)


@dataclass
class Calibrator:
    name: str
    predict: Callable[[np.ndarray], np.ndarray]
    params: dict


# ── Platt scaling ────────────────────────────────────────────────────────────

def platt_scaling(conf: np.ndarray, outcomes: np.ndarray) -> Calibrator:
    """Fit logistic regression on raw confidence values."""
    from sklearn.linear_model import LogisticRegression

    x = _clamp01(conf).reshape(-1, 1)
    y = outcomes.astype(int)

    if len(np.unique(y)) < 2:
        # All-same outcome — cannot fit; return identity
        return Calibrator("platt_identity", lambda c: _clamp01(c), {"note": "single_class"})

    lr = LogisticRegression(solver="lbfgs")
    lr.fit(x, y)
    a = float(lr.coef_[0][0])
    b = float(lr.intercept_[0])

    def predict(c: np.ndarray) -> np.ndarray:
        c = _clamp01(np.asarray(c))
        return 1.0 / (1.0 + np.exp(-(a * c + b)))

    return Calibrator("platt_scaling", predict, {"a": a, "b": b})


# ── Isotonic regression ─────────────────────────────────────────────────────

def isotonic_regression(conf: np.ndarray, outcomes: np.ndarray) -> Calibrator:
    """Non-parametric monotonic mapping."""
    from sklearn.isotonic import IsotonicRegression

    x = _clamp01(conf)
    y = outcomes.astype(float)

    ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    ir.fit(x, y)

    def predict(c: np.ndarray) -> np.ndarray:
        return _clamp01(ir.predict(_clamp01(np.asarray(c))))

    return Calibrator("isotonic_regression", predict,
                      {"n_thresholds": len(ir.X_thresholds_)
                        if hasattr(ir, "X_thresholds_") else 0})


# ── Histogram binning ───────────────────────────────────────────────────────

def histogram_binning(conf: np.ndarray, outcomes: np.ndarray,
                       n_bins: int = 10) -> Calibrator:
    """Bin raw confidence into N buckets, replace each with empirical win-rate."""
    x = _clamp01(conf)
    y = outcomes.astype(int)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(x, bin_edges[1:-1])
    bin_means = np.zeros(n_bins)
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() > 0:
            bin_means[b] = float(y[mask].mean())
        else:
            # Empty bin — use bin midpoint as fallback
            bin_means[b] = float((bin_edges[b] + bin_edges[b + 1]) / 2)

    def predict(c: np.ndarray) -> np.ndarray:
        c = _clamp01(np.asarray(c))
        idx = np.digitize(c, bin_edges[1:-1])
        return _clamp01(bin_means[idx])

    return Calibrator("histogram_binning", predict,
                      {"n_bins": n_bins, "bin_edges": bin_edges.tolist(),
                        "bin_means": bin_means.tolist()})


# ── Beta calibration (Kull et al. 2017) ─────────────────────────────────────

def beta_calibration(conf: np.ndarray, outcomes: np.ndarray) -> Calibrator:
    """Beta-distribution based parametric calibration.

    Fits P(y=1|p) = sigmoid(a*log(p) + b*log(1-p) + c) via logistic regression
    on the log-transformed features.
    """
    from sklearn.linear_model import LogisticRegression

    x = _clamp01(conf)
    y = outcomes.astype(int)

    if len(np.unique(y)) < 2:
        return Calibrator("beta_identity", lambda c: _clamp01(c), {"note": "single_class"})

    # Two features: log(p) and log(1-p)
    features = np.column_stack([np.log(x), np.log(1 - x)])

    lr = LogisticRegression(solver="lbfgs")
    lr.fit(features, y)
    a = float(lr.coef_[0][0])
    b = float(lr.coef_[0][1])
    c = float(lr.intercept_[0])

    def predict(x_in: np.ndarray) -> np.ndarray:
        x_in = _clamp01(np.asarray(x_in))
        z = a * np.log(x_in) + b * np.log(1 - x_in) + c
        return _clamp01(1.0 / (1.0 + np.exp(-z)))

    return Calibrator("beta_calibration", predict, {"a": a, "b": b, "c": c})


# ── Temperature scaling ─────────────────────────────────────────────────────

def temperature_scaling(conf: np.ndarray, outcomes: np.ndarray) -> Calibrator:
    """For binary probabilities: p_cal = sigmoid(logit(p) / T). Fit T by minimising NLL."""
    from scipy.optimize import minimize_scalar

    x = _clamp01(conf)
    y = outcomes.astype(float)
    logits = np.log(x / (1 - x))

    def neg_log_likelihood(T: float) -> float:
        if T <= 0:
            return 1e9
        p_cal = 1.0 / (1.0 + np.exp(-logits / T))
        p_cal = _clamp01(p_cal)
        return float(-(y * np.log(p_cal) + (1 - y) * np.log(1 - p_cal)).mean())

    res = minimize_scalar(neg_log_likelihood, bounds=(0.01, 10.0), method="bounded")
    T = float(res.x) if res.success else 1.0

    def predict(c: np.ndarray) -> np.ndarray:
        c = _clamp01(np.asarray(c))
        lg = np.log(c / (1 - c))
        return _clamp01(1.0 / (1.0 + np.exp(-lg / T)))

    return Calibrator("temperature_scaling", predict, {"T": T})


# ── Registry ─────────────────────────────────────────────────────────────────

METHODS: dict[str, Callable] = {
    "platt_scaling":         platt_scaling,
    "isotonic_regression":   isotonic_regression,
    "histogram_binning":     histogram_binning,
    "beta_calibration":      beta_calibration,
    "temperature_scaling":   temperature_scaling,
}


def fit_all(conf: np.ndarray, outcomes: np.ndarray) -> dict[str, Calibrator]:
    """Fit every calibration method on the same (conf, outcome) data."""
    return {name: fn(conf, outcomes) for name, fn in METHODS.items()}
