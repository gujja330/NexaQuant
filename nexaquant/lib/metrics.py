"""Pure metric helpers.

Consolidates 15+ scattered implementations of Sharpe / MaxDD / annualization
identified in the ENG001 audit (e.g. `backpaper.py:32`, `dynamic_policy.py:141`,
`aegis_dashboard.py:96`, `evidence/monte_carlo.py:31`, plus ~10 more).

Every function here is PURE:
- No file I/O
- No `sys.path` mutation
- No global state
- Deterministic on numeric inputs
- Fully type-annotated
- Docstring-covered

These helpers are drop-in replacements for the audited duplicates, but ENG001
does NOT rewire any existing caller. Migration is deferred to later phases so
each rewiring can be individually MON001-fingerprint-verified.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR: int = 252
NUMERICAL_EPS: float = 1e-12


def sharpe(returns: pd.Series | Sequence[float], *,
            trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sharpe ratio.

    Matches the canonical `returns.mean() / (returns.std() + eps) * sqrt(N)`
    idiom used across the audited codebase.

    Returns NaN if the input has fewer than 2 observations or zero variance.
    """
    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < 2:
        return float("nan")
    std = r.std()
    if std == 0 or not math.isfinite(std):
        return float("nan")
    return float(r.mean() / (std + NUMERICAL_EPS) * math.sqrt(trading_days))


def max_drawdown(equity: pd.Series | Sequence[float]) -> float:
    """Return the worst peak-to-trough drawdown as a negative fraction.

    Given an equity curve (cumulative value), returns e.g. -0.18 for an 18%
    drawdown. Matches `((eq.cummax() - eq) / eq.cummax()).max()` semantics but
    returns the value as a signed float (negative = drawdown).
    """
    eq = pd.Series(equity, dtype=float).dropna()
    if eq.empty:
        return float("nan")
    peak = eq.cummax()
    dd = (eq - peak) / peak.replace(0, NUMERICAL_EPS)
    return float(dd.min())


def cagr(equity: pd.Series | Sequence[float], *,
          trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    """Compound annual growth rate of an equity curve.

    Returns NaN if the input has fewer than 2 observations or the terminal
    value is non-positive.
    """
    eq = pd.Series(equity, dtype=float).dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0 or eq.iloc[-1] <= 0:
        return float("nan")
    years = len(eq) / trading_days
    if years <= 0:
        return float("nan")
    return float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0)


def ulcer_index(equity: pd.Series | Sequence[float]) -> float:
    """Ulcer Index: RMS of drawdowns expressed as percent."""
    eq = pd.Series(equity, dtype=float).dropna()
    if eq.empty:
        return float("nan")
    peak = eq.cummax()
    dd_pct = ((eq - peak) / peak.replace(0, NUMERICAL_EPS)) * 100
    return float(math.sqrt((dd_pct ** 2).mean()))


def annualized_vol(returns: pd.Series | Sequence[float], *,
                    trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < 2:
        return float("nan")
    return float(r.std() * math.sqrt(trading_days))


def sortino(returns: pd.Series | Sequence[float], *,
             trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sortino ratio (downside-only volatility in the denominator)."""
    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < 2:
        return float("nan")
    downside = r[r < 0]
    if downside.empty:
        return float("inf")
    dstd = downside.std()
    if dstd == 0 or not math.isfinite(dstd):
        return float("nan")
    return float(r.mean() / (dstd + NUMERICAL_EPS) * math.sqrt(trading_days))


def hit_rate(returns: pd.Series | Sequence[float]) -> float:
    """Fraction of strictly positive returns (0.0-1.0). NaN if empty."""
    r = pd.Series(returns, dtype=float).dropna()
    if r.empty:
        return float("nan")
    return float((r > 0).sum() / len(r))
