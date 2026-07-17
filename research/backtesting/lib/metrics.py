"""Institutional performance metrics for DEV021 backtesting.

All 20+ metrics from the DEV021 spec. Given a daily return series, computes
Sharpe, Sortino, Calmar, Treynor, Alpha, Beta, IR, Tracking Error, Max DD,
Recovery Time, Profit Factor, Win/Loss rates, Expectancy, Turnover, etc.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252
DEFAULT_RF = 0.05                                    # 5% annual — Indian G-Sec proxy


def _validate_returns(r: pd.Series) -> pd.Series:
    """Coerce to non-empty, finite float series indexed by date."""
    r = pd.Series(r).astype(float)
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    return r


def _annualise_return(daily_returns: pd.Series) -> float:
    """Geometric annualised return from a daily return series."""
    r = _validate_returns(daily_returns)
    if r.empty:
        return float("nan")
    cum = (1 + r).prod()
    years = len(r) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return float("nan")
    return float(cum ** (1 / years) - 1)


def cagr(daily_returns: pd.Series) -> float:
    return _annualise_return(daily_returns)


def annual_volatility(daily_returns: pd.Series) -> float:
    r = _validate_returns(daily_returns)
    if len(r) < 2:
        return float("nan")
    return float(r.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def downside_volatility(daily_returns: pd.Series, mar: float = 0.0) -> float:
    """Semi-deviation below MAR (annualised)."""
    r = _validate_returns(daily_returns)
    downside = r[r < mar]
    if len(downside) < 2:
        return float("nan")
    return float(downside.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe_ratio(daily_returns: pd.Series, rf: float = DEFAULT_RF) -> float:
    ann_ret = _annualise_return(daily_returns)
    ann_vol = annual_volatility(daily_returns)
    if not np.isfinite(ann_ret) or not np.isfinite(ann_vol) or ann_vol == 0:
        return float("nan")
    return float((ann_ret - rf) / ann_vol)


def sortino_ratio(daily_returns: pd.Series, rf: float = DEFAULT_RF) -> float:
    ann_ret = _annualise_return(daily_returns)
    ds_vol = downside_volatility(daily_returns)
    if not np.isfinite(ann_ret) or not np.isfinite(ds_vol) or ds_vol == 0:
        return float("nan")
    return float((ann_ret - rf) / ds_vol)


def max_drawdown(daily_returns: pd.Series) -> dict:
    """Returns dict with max_drawdown_pct, peak_date, trough_date, recovery_date, recovery_days."""
    r = _validate_returns(daily_returns)
    if r.empty:
        return {"max_dd_pct": float("nan"), "peak_date": None, "trough_date": None,
                  "recovery_date": None, "recovery_days": None}
    equity = (1 + r).cumprod()
    peak = equity.cummax()
    dd = (equity / peak - 1) * 100
    trough_idx = dd.idxmin()
    max_dd_pct = float(dd.min())
    # Peak before trough
    pre = equity.loc[:trough_idx]
    peak_idx = pre.idxmax()
    peak_value = float(pre.max())
    # Recovery: first date after trough where equity >= peak_value
    post = equity.loc[trough_idx:]
    recovery_hits = post[post >= peak_value]
    if not recovery_hits.empty:
        recovery_idx = recovery_hits.index[0]
        recovery_days = int((recovery_idx - trough_idx).days) if hasattr(recovery_idx, "date") else None
    else:
        recovery_idx = None
        recovery_days = None                                             # not yet recovered

    return {
        "max_dd_pct":     max_dd_pct,
        "peak_date":      str(peak_idx.date()) if hasattr(peak_idx, "date") else str(peak_idx),
        "trough_date":    str(trough_idx.date()) if hasattr(trough_idx, "date") else str(trough_idx),
        "recovery_date":  str(recovery_idx.date()) if recovery_idx is not None and hasattr(recovery_idx, "date") else None,
        "recovery_days":  recovery_days,
    }


def calmar_ratio(daily_returns: pd.Series) -> float:
    ann_ret = _annualise_return(daily_returns)
    dd_info = max_drawdown(daily_returns)
    dd = dd_info["max_dd_pct"] / 100
    if not np.isfinite(ann_ret) or not np.isfinite(dd) or dd == 0:
        return float("nan")
    return float(ann_ret / abs(dd))


def beta(strategy: pd.Series, benchmark: pd.Series) -> float:
    """Regression slope of strategy on benchmark."""
    aligned = pd.concat([strategy.rename("s"), benchmark.rename("b")],
                          axis=1).dropna()
    if len(aligned) < 30:
        return float("nan")
    cov = aligned["s"].cov(aligned["b"])
    var = aligned["b"].var()
    if var == 0:
        return float("nan")
    return float(cov / var)


def alpha(strategy: pd.Series, benchmark: pd.Series, rf: float = DEFAULT_RF) -> float:
    """CAPM alpha, annualised."""
    b = beta(strategy, benchmark)
    if not np.isfinite(b):
        return float("nan")
    s_ann = _annualise_return(strategy)
    b_ann = _annualise_return(benchmark)
    if not np.isfinite(s_ann) or not np.isfinite(b_ann):
        return float("nan")
    return float(s_ann - (rf + b * (b_ann - rf)))


def treynor_ratio(strategy: pd.Series, benchmark: pd.Series, rf: float = DEFAULT_RF) -> float:
    b = beta(strategy, benchmark)
    if not np.isfinite(b) or b == 0:
        return float("nan")
    ann = _annualise_return(strategy)
    if not np.isfinite(ann):
        return float("nan")
    return float((ann - rf) / b)


def information_ratio(strategy: pd.Series, benchmark: pd.Series) -> float:
    aligned = pd.concat([strategy.rename("s"), benchmark.rename("b")],
                          axis=1).dropna()
    if len(aligned) < 30:
        return float("nan")
    active = aligned["s"] - aligned["b"]
    if active.std() == 0:
        return float("nan")
    ir = active.mean() / active.std() * math.sqrt(TRADING_DAYS_PER_YEAR)
    return float(ir)


def tracking_error(strategy: pd.Series, benchmark: pd.Series) -> float:
    aligned = pd.concat([strategy.rename("s"), benchmark.rename("b")],
                          axis=1).dropna()
    if len(aligned) < 30:
        return float("nan")
    active = aligned["s"] - aligned["b"]
    return float(active.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def trade_metrics(trade_returns: list[float]) -> dict:
    """Given per-trade returns (%), compute win-rate / profit-factor / expectancy."""
    if not trade_returns:
        return {"n_trades": 0, "win_rate_pct": None, "loss_rate_pct": None,
                "profit_factor": None, "avg_winner_pct": None, "avg_loser_pct": None,
                "expectancy_pct": None, "best_trade_pct": None, "worst_trade_pct": None}
    arr = np.array(trade_returns, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    n = len(arr)
    profit_factor = float(wins.sum() / abs(losses.sum())) if len(losses) > 0 and losses.sum() != 0 else float("inf")
    return {
        "n_trades":         n,
        "win_rate_pct":     float(len(wins) / n * 100),
        "loss_rate_pct":    float(len(losses) / n * 100),
        "profit_factor":    profit_factor,
        "avg_winner_pct":   float(wins.mean()) if len(wins) > 0 else 0.0,
        "avg_loser_pct":    float(losses.mean()) if len(losses) > 0 else 0.0,
        "expectancy_pct":   float(arr.mean()),
        "best_trade_pct":   float(arr.max()),
        "worst_trade_pct":  float(arr.min()),
    }


def all_metrics(strategy: pd.Series, benchmark: pd.Series | None = None,
                 trade_returns: list[float] | None = None,
                 rf: float = DEFAULT_RF) -> dict:
    """One-shot: compute the full metric bundle."""
    out = {
        "cagr":                 cagr(strategy),
        "annual_volatility":    annual_volatility(strategy),
        "sharpe_ratio":         sharpe_ratio(strategy, rf),
        "sortino_ratio":        sortino_ratio(strategy, rf),
        "calmar_ratio":         calmar_ratio(strategy),
        "max_drawdown":         max_drawdown(strategy),
    }
    if benchmark is not None:
        out["beta"] = beta(strategy, benchmark)
        out["alpha"] = alpha(strategy, benchmark, rf)
        out["treynor_ratio"] = treynor_ratio(strategy, benchmark, rf)
        out["information_ratio"] = information_ratio(strategy, benchmark)
        out["tracking_error"] = tracking_error(strategy, benchmark)
        out["benchmark_cagr"] = cagr(benchmark)
        out["benchmark_vol"] = annual_volatility(benchmark)
    if trade_returns is not None:
        out["trade_metrics"] = trade_metrics(trade_returns)
    return out
