"""Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).

Adjusts a reported Sharpe for the number of independent trials that
produced it, correcting for selection / multiple-testing bias.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Sequence


def sharpe(returns: Sequence[float], periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio · zero risk-free rate (excess-return input assumed)."""
    if not returns:
        return 0.0
    mu = mean(returns)
    sd = pstdev(returns)
    if sd == 0:
        return 0.0
    return (mu / sd) * math.sqrt(periods_per_year)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    # Beasley-Springer / Moro approximation for the inverse normal CDF
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00,  2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    plow = 0.02425; phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1-p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q*q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe_ratio(observed_sr: float, n_trials: int,
                          n_returns: int,
                          skew: float = 0.0, kurt: float = 3.0) -> dict:
    """DSR test-statistic + p-value.

    observed_sr · non-annualized SR of the strategy that was SELECTED
    n_trials    · number of trials (parameter combinations) tried in the family
    n_returns   · number of return observations (T)
    skew, kurt  · higher moments of the return series (default normal)

    Returns { dsr_stat, p_value, expected_max_sr_from_selection }.
    """
    if n_returns <= 1 or n_trials < 1:
        return {"dsr_stat": None, "p_value": None,
                "expected_max_sr_from_selection": None}
    gamma = 0.5772156649        # Euler-Mascheroni
    # n_trials=1 · no selection bias · DSR collapses to raw SR t-stat.
    # Guard against ppf(0) / ppf(1) by capping the interior probability.
    if n_trials == 1:
        expected_max_sr = 0.0
    else:
        p_hi = 1.0 - 1.0 / n_trials
        p_lo = 1.0 - 1.0 / (n_trials * math.e)
        # Clamp to open interval to avoid inf; caps only matter for tiny/huge n_trials.
        p_hi = min(max(p_hi, 1e-9), 1.0 - 1e-9)
        p_lo = min(max(p_lo, 1e-9), 1.0 - 1e-9)
        expected_max_sr = (
            (1.0 - gamma) * _norm_ppf(p_hi)
            + gamma * _norm_ppf(p_lo)
        )
    denom_sq = (1.0
                - skew * observed_sr
                + ((kurt - 1.0) / 4.0) * observed_sr * observed_sr)
    if denom_sq <= 0:
        return {"dsr_stat": None, "p_value": None,
                "expected_max_sr_from_selection": expected_max_sr}
    num = (observed_sr - expected_max_sr) * math.sqrt(n_returns - 1)
    dsr = num / math.sqrt(denom_sq)
    p = 1.0 - _norm_cdf(dsr)
    return {
        "dsr_stat": dsr,
        "p_value": p,
        "expected_max_sr_from_selection": expected_max_sr,
    }
