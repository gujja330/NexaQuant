"""Concentration metrics — HHI and top-K exposure."""
from __future__ import annotations


def herfindahl_hirschman(weights: list[float]) -> float:
    """HHI = sum of squared weights. 0..1. 1 = single-position portfolio.

    Uses absolute weights so a long/short book measures concentration on gross basis.
    """
    if not weights: return 0.0
    total = sum(abs(w) for w in weights)
    if total <= 0: return 0.0
    normed = [abs(w) / total for w in weights]
    return sum(w * w for w in normed)


def top_k_concentration_pct(weights: list[float], k: int = 5) -> float:
    """What fraction of gross exposure sits in the top-K positions."""
    if not weights: return 0.0
    abs_w = sorted((abs(w) for w in weights), reverse=True)
    total = sum(abs_w)
    if total <= 0: return 0.0
    return sum(abs_w[:k]) / total
