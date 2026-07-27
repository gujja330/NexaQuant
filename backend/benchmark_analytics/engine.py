"""Benchmark Analytics Engine · full institutional metric panel.

Given a return series and a benchmark series, compute the standard
institutional performance metrics. All inputs/outputs deterministic.

Uses the shared indicator library (Article 30) for the underlying math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from statistics import mean, stdev
from typing import Sequence

SCHEMA_FINGERPRINT = "aegis.benchmark_analytics.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.benchmark_analytics.v1"

TRADING_DAYS_YEAR = 252


@dataclass(frozen=True)
class PerformanceMetrics:
    n_obs: int
    total_return_pct: float
    annualized_return_pct: float
    annualized_vol_pct: float
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    information_ratio: float | None
    alpha_pct: float | None       # annualized · vs benchmark
    beta: float | None            # OLS slope
    hit_ratio: float | None       # % positive periods
    max_drawdown_pct: float | None
    tracking_error_pct: float | None
    win_loss_ratio: float | None
    profit_factor: float | None
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


def _pct(v): return round(float(v) * 100, 4) if v is not None else None
def _round(v, n=4): return round(float(v), n) if v is not None else None


def _annualize_return(daily_returns: Sequence[float]) -> float:
    """Geometric annualized return from daily returns."""
    if not daily_returns: return 0.0
    cum = 1.0
    for r in daily_returns:
        cum *= (1.0 + r)
    if cum <= 0: return -1.0
    years = len(daily_returns) / TRADING_DAYS_YEAR
    if years <= 0: return 0.0
    return cum ** (1.0 / years) - 1.0


def _annualize_vol(daily_returns: Sequence[float]) -> float:
    if len(daily_returns) < 2: return 0.0
    return stdev(daily_returns) * math.sqrt(TRADING_DAYS_YEAR)


def _max_drawdown(daily_returns: Sequence[float]) -> float:
    """Max drawdown of cumulative return curve · negative pct."""
    if not daily_returns: return 0.0
    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        cum *= (1.0 + r)
        if cum > peak: peak = cum
        dd = cum / peak - 1.0
        if dd < max_dd: max_dd = dd
    return max_dd  # already ≤ 0


def _ols_beta_alpha(rets: Sequence[float], bench: Sequence[float]) -> tuple[float | None, float | None]:
    """Beta = Cov(r,b) / Var(b) · Alpha = mean(r) - Beta*mean(b) (annualized)."""
    n = min(len(rets), len(bench))
    if n < 3: return None, None
    r = list(rets[:n]); b = list(bench[:n])
    mr = mean(r); mb = mean(b)
    cov = sum((r[i]-mr)*(b[i]-mb) for i in range(n)) / n
    var_b = sum((b[i]-mb)**2 for i in range(n)) / n
    if var_b == 0: return None, None
    beta = cov / var_b
    daily_alpha = mr - beta * mb
    annual_alpha = daily_alpha * TRADING_DAYS_YEAR
    return round(beta, 6), round(annual_alpha, 6)


def _sharpe(rets: Sequence[float], rf_daily: float = 0.0) -> float | None:
    if len(rets) < 2: return None
    ex = [r - rf_daily for r in rets]
    m = mean(ex); s = stdev(ex)
    if s == 0: return None
    return round((m / s) * math.sqrt(TRADING_DAYS_YEAR), 4)


def _sortino(rets: Sequence[float], rf_daily: float = 0.0) -> float | None:
    if len(rets) < 2: return None
    ex = [r - rf_daily for r in rets]
    downside = [e for e in ex if e < 0]
    if not downside: return None
    m = mean(ex)
    ds = math.sqrt(sum(d*d for d in downside) / len(downside))
    if ds == 0: return None
    return round((m / ds) * math.sqrt(TRADING_DAYS_YEAR), 4)


def _information_ratio(rets: Sequence[float], bench: Sequence[float]) -> tuple[float | None, float | None]:
    n = min(len(rets), len(bench))
    if n < 2: return None, None
    active = [rets[i] - bench[i] for i in range(n)]
    m = mean(active); s = stdev(active) if len(active) >= 2 else 0
    if s == 0: return None, round(s * math.sqrt(TRADING_DAYS_YEAR) * 100, 4)
    ir = (m / s) * math.sqrt(TRADING_DAYS_YEAR)
    tracking_error = s * math.sqrt(TRADING_DAYS_YEAR)
    return round(ir, 4), round(tracking_error * 100, 4)


def _hit_ratio(rets: Sequence[float]) -> float | None:
    if not rets: return None
    pos = sum(1 for r in rets if r > 0)
    return round(pos / len(rets), 4)


def _win_loss_ratio(rets: Sequence[float]) -> tuple[float | None, float | None]:
    wins = [r for r in rets if r > 0]
    losses = [-r for r in rets if r < 0]
    if not wins or not losses: return None, None
    wl = mean(wins) / mean(losses) if losses else None
    pf = sum(wins) / sum(losses) if sum(losses) > 0 else None
    return (round(wl, 4) if wl else None), (round(pf, 4) if pf else None)


class BenchmarkAnalytics:

    def compute(self, returns: Sequence[float],
                 benchmark_returns: Sequence[float] | None = None,
                 rf_daily: float = 0.0) -> PerformanceMetrics:
        if not returns:
            return PerformanceMetrics(0, 0.0, 0.0, 0.0, None, None, None, None,
                                       None, None, None, None, None, None, None)
        ann_ret = _annualize_return(returns)
        ann_vol = _annualize_vol(returns)
        sharpe = _sharpe(returns, rf_daily)
        sortino = _sortino(returns, rf_daily)
        max_dd = _max_drawdown(returns)
        calmar = round(ann_ret / abs(max_dd), 4) if max_dd < 0 else None
        hit = _hit_ratio(returns)
        wl, pf = _win_loss_ratio(returns)
        alpha = beta = ir = te = None
        if benchmark_returns:
            beta, alpha = _ols_beta_alpha(returns, benchmark_returns)
            ir, te = _information_ratio(returns, benchmark_returns)
        total_ret = 1.0
        for r in returns: total_ret *= (1.0 + r)
        total_ret -= 1.0
        return PerformanceMetrics(
            n_obs=len(returns),
            total_return_pct=_pct(total_ret),
            annualized_return_pct=_pct(ann_ret),
            annualized_vol_pct=_pct(ann_vol),
            sharpe=sharpe, sortino=sortino, calmar=calmar,
            information_ratio=ir,
            alpha_pct=_pct(alpha),
            beta=beta,
            hit_ratio=hit,
            max_drawdown_pct=_pct(max_dd),
            tracking_error_pct=te,
            win_loss_ratio=wl,
            profit_factor=pf,
        )


def compute_metrics(returns, benchmark_returns=None, rf_daily=0.0) -> dict:
    return asdict(BenchmarkAnalytics().compute(returns, benchmark_returns, rf_daily))
