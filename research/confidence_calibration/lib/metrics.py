"""DEV029 calibration metrics.

Every metric operates on (predicted_probabilities, actual_outcomes) pairs.
"""
from __future__ import annotations

import numpy as np


EPS = 1e-12


def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    """MSE of predicted probability vs actual outcome. Lower is better."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Weighted mean absolute gap between predicted and observed win rate per bin."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = mask.sum()
        if n == 0:
            continue
        avg_p = float(p[mask].mean())
        avg_y = float(y[mask].mean())
        total += (n / len(p)) * abs(avg_p - avg_y)
    return float(total)


def maximum_calibration_error(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Worst-bin |predicted - observed|."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    max_gap = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = mask.sum()
        if n == 0:
            continue
        avg_p = float(p[mask].mean())
        avg_y = float(y[mask].mean())
        max_gap = max(max_gap, abs(avg_p - avg_y))
    return float(max_gap)


def reliability_score(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """The "resolution + reliability" decomposition of Brier score. Lower = better."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = mask.sum()
        if n == 0:
            continue
        avg_p = float(p[mask].mean())
        avg_y = float(y[mask].mean())
        total += (n / len(p)) * (avg_p - avg_y) ** 2
    return float(total)


def sharpness(p: np.ndarray) -> float:
    """Variance of predicted probabilities. Higher = sharper (bolder) predictions."""
    p = np.asarray(p, dtype=float)
    if len(p) < 2:
        return 0.0
    return float(np.var(p))


def confidence_bias(p: np.ndarray, y: np.ndarray) -> float:
    """Mean(predicted) - mean(actual). Positive = overconfident on average."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return float("nan")
    return float(np.mean(p) - np.mean(y))


def reliability_curve(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Per-bin reliability data for plotting."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(p) == 0:
        return []
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        if n == 0:
            rows.append({"bin_lo": float(lo), "bin_hi": float(hi),
                          "n": 0, "predicted": None, "observed": None, "gap": None})
        else:
            avg_p = float(p[mask].mean())
            avg_y = float(y[mask].mean())
            rows.append({"bin_lo": float(lo), "bin_hi": float(hi),
                          "n": n, "predicted": round(avg_p, 4),
                          "observed": round(avg_y, 4), "gap": round(avg_p - avg_y, 4)})
    return rows


def all_metrics(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> dict:
    return {
        "brier_score":       round(brier_score(p, y), 6),
        "log_loss":          round(log_loss(p, y), 6),
        "ece":               round(expected_calibration_error(p, y, n_bins), 6),
        "mce":               round(maximum_calibration_error(p, y, n_bins), 6),
        "reliability_score": round(reliability_score(p, y, n_bins), 6),
        "sharpness":         round(sharpness(p), 6),
        "confidence_bias":   round(confidence_bias(p, y), 6),
    }
