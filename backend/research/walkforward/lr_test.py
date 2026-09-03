"""Likelihood-ratio test for nested models (P4 · Cap only vs Cap + Sector).

  LR = 2 * (loglik_full - loglik_restricted)
  df = param_full - param_restricted
  p  = 1 - chi2_cdf(LR, df)

Uses a numeric chi-square CDF (Wilson-Hilferty approximation) so we do
not require scipy at runtime.
"""
from __future__ import annotations

import math


def _chi2_cdf(x: float, df: int) -> float:
    """Wilson-Hilferty approx · valid for df >= 1, x >= 0."""
    if x <= 0 or df < 1: return 0.0
    h = 2.0 / (9.0 * df)
    z = (math.pow(x / df, 1.0/3.0) - (1.0 - h)) / math.sqrt(h)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def lr_test(loglik_full: float, loglik_restricted: float,
            df_diff: int) -> dict:
    """Return { lr_stat, p_value, df }."""
    if df_diff <= 0:
        return {"lr_stat": None, "p_value": None, "df": df_diff}
    lr = 2.0 * (loglik_full - loglik_restricted)
    if lr < 0: lr = 0.0
    p = 1.0 - _chi2_cdf(lr, df_diff)
    return {"lr_stat": lr, "p_value": p, "df": df_diff}
