"""Performance metrics — canonical implementations.

Every metric is a pure function of numpy arrays / pandas series. No random
state. Deterministic. Every downstream engine imports from here so Sharpe
computed in the Execution Simulator matches Sharpe in the Walk-Forward
Auditor exactly.

Version bump policy: if a formula changes (rare — most are locked), bump
METRICS_VERSION and add a `docs/AEGIS_SCHEMA_CHANGELOG.md` entry.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


METRICS_VERSION = "1.0.0"

TRADING_DAYS_PER_YEAR = 252


# ── Helpers ────────────────────────────────────────────────────
def _as_array(x: Sequence[float]) -> np.ndarray:
    if x is None:
        return np.array([], dtype=float)
    a = np.asarray(x, dtype=float)
    return a[~np.isnan(a)]


# ── Return-based ───────────────────────────────────────────────
def cagr(equity_curve: Sequence[float]) -> float | None:
    """Compound annualised growth rate from an equity curve (list of values).

    Requires ≥ 2 points. Returns None if not enough data or non-positive start.
    """
    e = _as_array(equity_curve)
    if len(e) < 2 or e[0] <= 0:
        return None
    total = float(e[-1] / e[0])
    if total <= 0: return None
    years = (len(e) - 1) / TRADING_DAYS_PER_YEAR
    if years <= 0: return None
    return float(total ** (1.0 / years) - 1.0)


def sharpe_ratio(daily_returns: Sequence[float],
                    risk_free_daily: float = 0.0) -> float | None:
    """Annualised Sharpe ratio."""
    r = _as_array(daily_returns) - risk_free_daily
    if len(r) < 2 or r.std(ddof=0) == 0:
        return None
    return float(r.mean() / r.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(daily_returns: Sequence[float],
                     risk_free_daily: float = 0.0) -> float | None:
    """Annualised Sortino ratio (downside-only volatility)."""
    r = _as_array(daily_returns) - risk_free_daily
    downside = r[r < 0]
    if len(r) < 2 or len(downside) == 0 or downside.std(ddof=0) == 0:
        return None
    return float(r.mean() / downside.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity_curve: Sequence[float]) -> float | None:
    """Maximum peak-to-trough drawdown as a negative number (e.g. -0.25 = -25%)."""
    e = _as_array(equity_curve)
    if len(e) < 2:
        return None
    running_max = np.maximum.accumulate(e)
    dd = (e / running_max) - 1.0
    return float(dd.min())


def calmar_ratio(equity_curve: Sequence[float]) -> float | None:
    """CAGR / |max_drawdown|."""
    c = cagr(equity_curve)
    mdd = max_drawdown(equity_curve)
    if c is None or mdd is None or mdd == 0:
        return None
    return float(c / abs(mdd))


def recovery_factor(equity_curve: Sequence[float]) -> float | None:
    """Total return / |max_drawdown|."""
    e = _as_array(equity_curve)
    if len(e) < 2 or e[0] <= 0:
        return None
    total_return = float(e[-1] / e[0] - 1.0)
    mdd = max_drawdown(equity_curve)
    if mdd is None or mdd == 0:
        return None
    return float(total_return / abs(mdd))


# ── Trade-based ────────────────────────────────────────────────
def profit_factor(trade_returns: Sequence[float]) -> float | None:
    r = _as_array(trade_returns)
    if len(r) == 0: return None
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return None if wins == 0 else float("inf")
    return float(wins / losses)


def hit_rate(trade_returns: Sequence[float]) -> float | None:
    r = _as_array(trade_returns)
    if len(r) == 0: return None
    return float((r > 0).sum() / len(r))


def expected_value(trade_returns: Sequence[float]) -> float | None:
    r = _as_array(trade_returns)
    if len(r) == 0: return None
    return float(r.mean())


def avg_winner(trade_returns: Sequence[float]) -> float | None:
    r = _as_array(trade_returns)
    wins = r[r > 0]
    return float(wins.mean()) if len(wins) else None


def avg_loser(trade_returns: Sequence[float]) -> float | None:
    r = _as_array(trade_returns)
    losses = r[r < 0]
    return float(losses.mean()) if len(losses) else None


def avg_holding_period_days(holding_days: Sequence[float]) -> float | None:
    h = _as_array(holding_days)
    return float(h.mean()) if len(h) else None


def turnover(weight_changes: Sequence[float]) -> float:
    """Sum of |weight changes| across a rebalance / 2 (standard convention)."""
    w = _as_array(weight_changes)
    return float(np.abs(w).sum() / 2.0)


# ── Benchmark-relative ─────────────────────────────────────────
def information_ratio(portfolio_returns: Sequence[float],
                         benchmark_returns: Sequence[float]) -> float | None:
    p = _as_array(portfolio_returns)
    b = _as_array(benchmark_returns)
    n = min(len(p), len(b))
    if n < 2: return None
    diff = p[:n] - b[:n]
    if diff.std(ddof=0) == 0: return None
    return float(diff.mean() / diff.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))


def tracking_error(portfolio_returns: Sequence[float],
                     benchmark_returns: Sequence[float]) -> float | None:
    p = _as_array(portfolio_returns)
    b = _as_array(benchmark_returns)
    n = min(len(p), len(b))
    if n < 2: return None
    return float((p[:n] - b[:n]).std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))


def alpha_beta(portfolio_returns: Sequence[float],
                 benchmark_returns: Sequence[float],
                 risk_free_daily: float = 0.0) -> tuple[float | None, float | None]:
    """Alpha (annualised) + beta from OLS on excess returns."""
    p = _as_array(portfolio_returns) - risk_free_daily
    b = _as_array(benchmark_returns) - risk_free_daily
    n = min(len(p), len(b))
    if n < 3: return None, None
    p2, b2 = p[:n], b[:n]
    var_b = b2.var(ddof=0)
    if var_b == 0: return None, None
    beta = float(np.cov(p2, b2, ddof=0)[0, 1] / var_b)
    alpha_daily = float(p2.mean() - beta * b2.mean())
    alpha_ann = float(alpha_daily * TRADING_DAYS_PER_YEAR)
    return alpha_ann, beta
