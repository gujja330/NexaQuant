"""Parametric portfolio VaR + CVaR.

Sprint 4 baseline uses a normal-distribution approximation with per-ticker
20-day annualised volatility from the Feature Store. Sprint 8+ walk-forward
can validate the approximation against realised drawdowns and upgrade if
needed.
"""
from __future__ import annotations

import math


# 95% one-sided normal critical value
Z_95 = 1.6448536269514722


def _phi(z: float) -> float:
    """Standard-normal PDF."""
    return math.exp(-z * z / 2.0) / math.sqrt(2.0 * math.pi)


def parametric_var_cvar(weights: list[float], vols_annualised: list[float],
                          horizon_days: int = 1) -> tuple[float, float, float]:
    """Parametric 95% VaR + CVaR for a diagonal-covariance approximation.

    Assumes zero correlation across positions (conservative for a diversified book,
    but the point is fast + deterministic + directional; Sprint 8 validates against
    realised drawdowns).

    Args:
      weights:         signed portfolio weights per position
      vols_annualised: per-position annualised vol (same order as weights)
      horizon_days:    lookahead in days (default 1)

    Returns:
      (var_pct, cvar_pct, portfolio_vol_annualised) — all as *percent of portfolio value*,
       so 0.02 = 2%. Values are the LOSS side (positive numbers).
    """
    if not weights or not vols_annualised or len(weights) != len(vols_annualised):
        return 0.0, 0.0, 0.0

    # Portfolio annualised variance under zero-corr assumption
    port_var = sum((w * v) ** 2 for w, v in zip(weights, vols_annualised) if v > 0)
    port_vol_ann = math.sqrt(port_var) if port_var > 0 else 0.0

    # Scale to horizon
    scale = math.sqrt(horizon_days / 252.0)
    sigma_h = port_vol_ann * scale

    var_pct  = Z_95 * sigma_h
    # Analytic normal CVaR: phi(z_alpha) / (1 - alpha) × sigma
    cvar_pct = sigma_h * _phi(Z_95) / (1.0 - 0.95)

    return round(var_pct, 6), round(cvar_pct, 6), round(port_vol_ann, 6)
