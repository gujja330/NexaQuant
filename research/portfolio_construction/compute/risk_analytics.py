"""DEV022 portfolio-level risk analytics.

Given a portfolio (dict[ticker→weight]) and constituent price history:
  - Ex-ante portfolio volatility (from covariance matrix)
  - Beta vs Nifty 50
  - Sector / industry concentration (HHI + top-3 share)
  - Diversification ratio (Choueifaty-Coignard)
  - Effective N (Herfindahl-based)
  - Expected drawdown estimate
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "research"))


def _returns_matrix(weights: dict[str, float],
                     price_data: dict[str, pd.Series],
                     window: int = 252) -> pd.DataFrame:
    series = {}
    for t in weights:
        s = price_data.get(t)
        if s is None or len(s) < window + 5:
            continue
        r = s.pct_change().dropna().tail(window)
        if len(r) >= 30:
            series[t] = r
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1, join="inner").dropna()


def portfolio_volatility(weights: dict[str, float],
                          price_data: dict[str, pd.Series]) -> float | None:
    R = _returns_matrix(weights, price_data)
    if R.empty:
        return None
    cov = R.cov().values * 252
    tickers = R.columns.tolist()
    w = np.array([weights.get(t, 0) for t in tickers])
    if w.sum() == 0:
        return None
    w = w / w.sum()
    return float(math.sqrt(w @ cov @ w) * 100)


def portfolio_beta(weights: dict[str, float],
                    price_data: dict[str, pd.Series],
                    benchmark_series: pd.Series) -> float | None:
    R = _returns_matrix(weights, price_data)
    if R.empty or benchmark_series.empty:
        return None
    bench = benchmark_series[~benchmark_series.index.duplicated(keep="last")]
    bench_ret = bench.pct_change().dropna()
    aligned = pd.concat([R, bench_ret.rename("bench")], axis=1, join="inner").dropna()
    if len(aligned) < 30:
        return None
    port_ret = (aligned[R.columns.tolist()] *
                  [weights.get(t, 0) for t in R.columns]).sum(axis=1)
    aligned["port"] = port_ret
    cov = aligned["port"].cov(aligned["bench"])
    var = aligned["bench"].var()
    if var == 0:
        return None
    return float(cov / var)


def diversification_ratio(weights: dict[str, float],
                            price_data: dict[str, pd.Series]) -> float | None:
    R = _returns_matrix(weights, price_data)
    if R.empty:
        return None
    tickers = R.columns.tolist()
    w = np.array([weights.get(t, 0) for t in tickers])
    if w.sum() == 0:
        return None
    w = w / w.sum()
    cov = R.cov().values * 252
    sigma = np.sqrt(np.diag(cov))
    port_vol = math.sqrt(float(w @ cov @ w))
    if port_vol <= 0:
        return None
    return float((w @ sigma) / port_vol)


def concentration_stats(weights: dict[str, float], sector_map: dict[str, str],
                          industry_map: dict[str, str]) -> dict:
    """Herfindahl-Hirschman + top-3 shares for stocks, sectors, industries."""
    if not weights:
        return {}
    stock_hhi = float(sum(w * w for w in weights.values()))
    sorted_w = sorted(weights.values(), reverse=True)
    top3_stock = float(sum(sorted_w[:3]))

    sector_totals = defaultdict(float)
    for t, w in weights.items():
        sector_totals[sector_map.get(t, "Unknown")] += w
    sec_hhi = float(sum(v * v for v in sector_totals.values()))
    sec_sorted = sorted(sector_totals.values(), reverse=True)
    top3_sector = float(sum(sec_sorted[:3]))

    industry_totals = defaultdict(float)
    for t, w in weights.items():
        industry_totals[industry_map.get(t, "Unknown")] += w
    ind_hhi = float(sum(v * v for v in industry_totals.values()))
    ind_sorted = sorted(industry_totals.values(), reverse=True)
    top3_industry = float(sum(ind_sorted[:3]))

    # Effective N: 1/HHI
    return {
        "stock_hhi":               round(stock_hhi, 4),
        "effective_n_stocks":      round(1.0 / stock_hhi if stock_hhi > 0 else 0, 2),
        "top3_stock_share":        round(top3_stock, 4),
        "sector_hhi":              round(sec_hhi, 4),
        "effective_n_sectors":     round(1.0 / sec_hhi if sec_hhi > 0 else 0, 2),
        "top3_sector_share":       round(top3_sector, 4),
        "industry_hhi":            round(ind_hhi, 4),
        "effective_n_industries":  round(1.0 / ind_hhi if ind_hhi > 0 else 0, 2),
        "top3_industry_share":     round(top3_industry, 4),
        "sector_breakdown":        {k: round(v, 4) for k, v in
                                       sorted(sector_totals.items(), key=lambda kv: kv[1], reverse=True)},
        "industry_breakdown":      {k: round(v, 4) for k, v in
                                       sorted(industry_totals.items(), key=lambda kv: kv[1], reverse=True)},
    }


def expected_return(weights: dict[str, float],
                      price_data: dict[str, pd.Series],
                      window: int = 252) -> float | None:
    """Simple annualised expected return from historical mean × weights."""
    R = _returns_matrix(weights, price_data, window)
    if R.empty:
        return None
    mu = R.mean() * 252
    w = np.array([weights.get(t, 0) for t in R.columns])
    if w.sum() == 0:
        return None
    w = w / w.sum()
    return float((w @ mu.values) * 100)


def analyse(portfolio: dict, price_data: dict[str, pd.Series],
             benchmark_series: pd.Series) -> dict:
    """Full risk analytics bundle for one portfolio."""
    positions = portfolio.get("positions", [])
    if not positions:
        return {"status": "no_positions"}

    weights = {p["ticker"]: p["weight"] for p in positions}
    sector_map = {p["ticker"]: p["sector"] for p in positions}
    industry_map = {p["ticker"]: p["industry"] for p in positions}

    vol = portfolio_volatility(weights, price_data)
    beta = portfolio_beta(weights, price_data, benchmark_series)
    div_ratio = diversification_ratio(weights, price_data)
    conc = concentration_stats(weights, sector_map, industry_map)
    exp_ret = expected_return(weights, price_data)

    # Expected Sharpe (annualised historical proxy)
    exp_sharpe = None
    if vol and exp_ret and vol > 0:
        exp_sharpe = round((exp_ret / 100 - 0.05) / (vol / 100), 3)

    return {
        "annualised_volatility_pct":  round(vol, 3) if vol else None,
        "beta_vs_nifty":              round(beta, 3) if beta else None,
        "diversification_ratio":      round(div_ratio, 3) if div_ratio else None,
        "expected_annual_return_pct": round(exp_ret, 3) if exp_ret else None,
        "expected_sharpe":            exp_sharpe,
        "concentration":              conc,
    }
