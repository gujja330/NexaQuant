"""Adaptive Rec v2.0 · full metric panel + Precision@K.

Every experiment must report this panel (ADR-013)."""
from __future__ import annotations

import numpy as np


EPS = 1e-12


def brier(p: np.ndarray, y: np.ndarray) -> float:
    if len(p) == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    if len(p) == 0:
        return float("nan")
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    if len(p) == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = mask.sum()
        if n == 0:
            continue
        total += (n / len(p)) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return float(total)


def precision_at_k(p: np.ndarray, y: np.ndarray, k: int) -> float:
    if len(p) == 0 or k <= 0:
        return float("nan")
    k = min(k, len(p))
    order = np.argsort(-p)
    return float(y[order[:k]].mean())


def auc_roc(p: np.ndarray, y: np.ndarray) -> float:
    """Standard ROC AUC. Deterministic given a stable sort."""
    if len(p) == 0 or len(np.unique(y)) < 2:
        return float("nan")
    order = np.argsort(-p, kind="stable")
    y_sorted = y[order]
    pos = int(y_sorted.sum())
    neg = int(len(y_sorted) - pos)
    if pos == 0 or neg == 0:
        return float("nan")
    tpr_cum = 0.0
    fpr_cum = 0.0
    auc = 0.0
    prev_tpr = 0.0
    for label in y_sorted:
        if label == 1:
            tpr_cum += 1.0 / pos
        else:
            auc += tpr_cum / neg  # advance FPR
            prev_tpr = tpr_cum
    return float(auc)


def confidence_bias(p: np.ndarray, y: np.ndarray) -> float:
    if len(p) == 0:
        return float("nan")
    return float(np.mean(p) - np.mean(y))


def sharpness(p: np.ndarray) -> float:
    if len(p) < 2:
        return 0.0
    return float(np.var(p))


def expectancy_per_tier(p: np.ndarray, y: np.ndarray, returns: np.ndarray,
                          tiers: dict[str, tuple[float, float]] | None = None) -> dict[str, dict]:
    """Return per-tier {n, win_rate, expectancy (avg return), avg_win, avg_loss, profit_factor}.

    tiers is {tier_name: (lo, hi)}. Default = 5 tiers at [0,0.5,0.7,0.8,0.9,1.0]."""
    if tiers is None:
        edges = [0.0, 0.5, 0.7, 0.8, 0.9, 1.01]
        tiers = {}
        for i in range(len(edges) - 1):
            tiers[f"[{edges[i]:.2f}, {edges[i+1]:.2f})"] = (edges[i], edges[i + 1])
    result = {}
    for name, (lo, hi) in tiers.items():
        mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n == 0:
            result[name] = {"n": 0, "win_rate": None, "expectancy": None,
                              "avg_win": None, "avg_loss": None, "profit_factor": None}
            continue
        wr = float(y[mask].mean())
        rets = returns[mask]
        wins = rets[rets > 0]
        losses = rets[rets <= 0]
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0
        pf = (float(wins.sum()) / abs(float(losses.sum()))) if len(losses) and losses.sum() != 0 else None
        result[name] = {
            "n":            n,
            "win_rate":     round(wr, 4),
            "expectancy":   round(float(rets.mean()), 4),
            "avg_win":      round(avg_win, 4),
            "avg_loss":     round(avg_loss, 4),
            "profit_factor": round(pf, 4) if pf is not None else None,
        }
    return result


def full_panel(p: np.ndarray, y: np.ndarray, returns: np.ndarray | None = None) -> dict:
    panel = {
        "brier":              round(brier(p, y), 6),
        "log_loss":           round(log_loss(p, y), 6),
        "ece":                round(ece(p, y), 6),
        "auc":                round(auc_roc(p, y), 6),
        "confidence_bias":    round(confidence_bias(p, y), 6),
        "sharpness":          round(sharpness(p), 6),
        "precision_at_1":     round(precision_at_k(p, y, 1), 4),
        "precision_at_3":     round(precision_at_k(p, y, 3), 4),
        "precision_at_5":     round(precision_at_k(p, y, 5), 4),
        "precision_at_10":    round(precision_at_k(p, y, 10), 4),
        "precision_at_20":    round(precision_at_k(p, y, 20), 4),
    }
    if returns is not None and len(returns) == len(p):
        pos = returns[returns > 0]
        neg = returns[returns <= 0]
        panel.update({
            "avg_win":       round(float(pos.mean()), 4) if len(pos) else 0.0,
            "avg_loss":      round(float(neg.mean()), 4) if len(neg) else 0.0,
            "expectancy":    round(float(returns.mean()), 4),
            "profit_factor": round(float(pos.sum()) / abs(float(neg.sum())), 4) if len(neg) and neg.sum() != 0 else None,
        })
    return panel
