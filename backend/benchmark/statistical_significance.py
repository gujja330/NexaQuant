"""
Sprint 7.8 · Statistical significance utilities.

Wilson score interval for win-rate proportions and Student-t interval for
mean returns. Pure numpy — no scipy dependency to keep the free-stack lean.
"""
from __future__ import annotations
import math
from typing import Optional, Tuple


def wilson_confidence_interval(n_wins: int, n_total: int, z: float = 1.96) -> Tuple[float, float, float]:
    """
    95% Wilson score CI for a Bernoulli proportion. Robust for small n.

    Returns (point_estimate, ci_low, ci_high). All in [0, 1].
    """
    if n_total <= 0:
        return (0.0, 0.0, 1.0)
    p_hat = n_wins / n_total
    denom = 1 + z * z / n_total
    centre = (p_hat + z * z / (2 * n_total)) / denom
    half = (z * math.sqrt(p_hat * (1 - p_hat) / n_total + z * z / (4 * n_total * n_total))) / denom
    return (round(p_hat, 6), round(max(0.0, centre - half), 6), round(min(1.0, centre + half), 6))


def mean_confidence_interval(mean: float, std: float, n: int, z: float = 1.96) -> Tuple[float, float, float]:
    """
    Approximate 95% CI for a mean using the normal-approx (n >= 30) or the
    z-score (small n — technically Student-t would be sharper; we flag the
    sample-size caveat separately via `sample_size_verdict`).
    """
    if n <= 0 or std <= 0:
        return (round(mean, 6), round(mean, 6), round(mean, 6))
    se = std / math.sqrt(n)
    half = z * se
    return (round(mean, 6), round(mean - half, 6), round(mean + half, 6))


def sample_size_verdict(n: int, *, min_directional: int = 5,
                          min_significant: int = 30, min_institutional: int = 100) -> str:
    """
    Structural verdict on sample size — never a "good/bad" claim.

    - n < min_directional        → INSUFFICIENT_DATA
    - min_directional ≤ n < min_significant → DIRECTIONAL_ONLY (interesting, not proven)
    - min_significant ≤ n < min_institutional → STATISTICALLY_MEANINGFUL
    - n ≥ min_institutional      → INSTITUTIONAL_GRADE
    """
    if n < min_directional:
        return "INSUFFICIENT_DATA"
    if n < min_significant:
        return "DIRECTIONAL_ONLY"
    if n < min_institutional:
        return "STATISTICALLY_MEANINGFUL"
    return "INSTITUTIONAL_GRADE"
