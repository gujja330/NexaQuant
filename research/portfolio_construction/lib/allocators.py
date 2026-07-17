"""DEV022 position-sizing algorithms.

All allocators accept:
  - candidates: list of {"ticker": str, "score": float, "confidence": float,
                          "sector": str, "industry": str}
  - price_data: optional dict[ticker → pd.Series] for vol/correlation-based methods

Return: dict[ticker → weight] (weights sum to 1.0).
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform


# ── Simple deterministic sizings ─────────────────────────────────────────────

def equal_weight(candidates: list[dict], **kw) -> dict[str, float]:
    if not candidates:
        return {}
    w = 1.0 / len(candidates)
    return {c["ticker"]: w for c in candidates}


def score_weight(candidates: list[dict], min_score: float = 50.0, **kw) -> dict[str, float]:
    filtered = [(c["ticker"], max(0.0, c["score"] - min_score)) for c in candidates]
    total = sum(s for _, s in filtered)
    if total <= 0:
        return equal_weight(candidates)
    return {t: s / total for t, s in filtered}


def confidence_weight(candidates: list[dict], **kw) -> dict[str, float]:
    filtered = [(c["ticker"], c.get("confidence", 1.0)) for c in candidates]
    total = sum(s for _, s in filtered)
    if total <= 0:
        return equal_weight(candidates)
    return {t: s / total for t, s in filtered}


def score_x_confidence_weight(candidates: list[dict], min_score: float = 50.0, **kw) -> dict[str, float]:
    filtered = [(c["ticker"], max(0.0, c["score"] - min_score) * c.get("confidence", 1.0))
                for c in candidates]
    total = sum(s for _, s in filtered)
    if total <= 0:
        return equal_weight(candidates)
    return {t: s / total for t, s in filtered}


# ── Volatility-based sizings ─────────────────────────────────────────────────

def _annualised_vol(series: pd.Series, window: int = 63) -> float:
    r = series.pct_change().dropna().tail(window)
    if len(r) < 5:
        return float("nan")
    return float(r.std() * math.sqrt(252))


def inverse_volatility_weight(candidates: list[dict],
                                 price_data: dict[str, pd.Series] | None = None,
                                 window: int = 63, **kw) -> dict[str, float]:
    if price_data is None:
        return equal_weight(candidates)
    weights = {}
    for c in candidates:
        s = price_data.get(c["ticker"])
        if s is None or len(s) < window + 5:
            continue
        vol = _annualised_vol(s, window)
        if not math.isfinite(vol) or vol <= 0:
            continue
        weights[c["ticker"]] = 1.0 / vol
    if not weights:
        return equal_weight(candidates)
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def volatility_weight(candidates: list[dict],
                        price_data: dict[str, pd.Series] | None = None, **kw) -> dict[str, float]:
    """Higher vol → higher weight (aggressive)."""
    if price_data is None:
        return equal_weight(candidates)
    weights = {}
    for c in candidates:
        s = price_data.get(c["ticker"])
        if s is None or len(s) < 68:
            continue
        vol = _annualised_vol(s)
        if not math.isfinite(vol) or vol <= 0:
            continue
        weights[c["ticker"]] = vol
    if not weights:
        return equal_weight(candidates)
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


# ── Correlation-based sizings ────────────────────────────────────────────────

def _returns_matrix(candidates: list[dict], price_data: dict[str, pd.Series],
                     window: int = 252) -> pd.DataFrame:
    """Aligned returns matrix; drops tickers with insufficient history."""
    series_by_ticker = {}
    for c in candidates:
        s = price_data.get(c["ticker"])
        if s is None or len(s) < window + 5:
            continue
        r = s.pct_change().dropna().tail(window)
        if len(r) >= 30:
            series_by_ticker[c["ticker"]] = r
    if not series_by_ticker:
        return pd.DataFrame()
    df = pd.concat(series_by_ticker, axis=1, join="inner").dropna()
    return df


def hierarchical_risk_parity(candidates: list[dict],
                                price_data: dict[str, pd.Series] | None = None,
                                **kw) -> dict[str, float]:
    """López de Prado 2016 HRP.

    Steps:
      1. Compute correlation matrix → distance matrix
      2. Hierarchical clustering (single-linkage)
      3. Quasi-diagonalisation
      4. Recursive bisection → weights
    """
    if price_data is None:
        return equal_weight(candidates)
    R = _returns_matrix(candidates, price_data)
    if R.empty or R.shape[1] < 2:
        return equal_weight(candidates)

    cov = R.cov().values * 252                                          # annualised
    corr = R.corr().values
    # Distance = sqrt(0.5 * (1 - corr))
    dist = np.sqrt(0.5 * (1 - corr))
    np.fill_diagonal(dist, 0.0)

    # Hierarchical clustering
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="single")

    # Quasi-diagonalisation: reorder by leaves in tree order
    def _quasi_diag(link):
        link = link.astype(int)
        n = link[-1, 3]                                                  # total leaves
        order = [link[-1, 0], link[-1, 1]]
        n_items = n
        while max(order) >= n_items:
            new_order = []
            for i in order:
                if i < n_items:
                    new_order.append(i)
                else:
                    row = link[i - n_items]
                    new_order.extend([row[0], row[1]])
            order = new_order
        return order

    sorted_idx = _quasi_diag(Z)
    tickers = R.columns.tolist()
    sorted_tickers = [tickers[i] for i in sorted_idx]

    # Recursive bisection
    def _cluster_var(cov_mat, indices):
        sub_cov = cov_mat[np.ix_(indices, indices)]
        inv_diag = 1.0 / np.diag(sub_cov)
        w = inv_diag / inv_diag.sum()
        return float(w @ sub_cov @ w)

    weights = pd.Series(1.0, index=sorted_tickers)
    clusters = [list(range(len(sorted_tickers)))]

    while clusters:
        clusters = [c[start:end]
                     for c in clusters if len(c) > 1
                     for start, end in ((0, len(c) // 2), (len(c) // 2, len(c)))
                     if end > start]
        for i in range(0, len(clusters), 2):
            if i + 1 >= len(clusters):
                break
            c0 = clusters[i]
            c1 = clusters[i + 1]
            v0 = _cluster_var(cov, [tickers.index(sorted_tickers[j]) for j in c0])
            v1 = _cluster_var(cov, [tickers.index(sorted_tickers[j]) for j in c1])
            if v0 + v1 == 0:
                continue
            alpha = 1 - v0 / (v0 + v1)
            for j in c0:
                weights.iloc[j] *= alpha
            for j in c1:
                weights.iloc[j] *= 1 - alpha

    # Normalise
    total = weights.sum()
    if total <= 0:
        return equal_weight(candidates)
    return {t: float(w / total) for t, w in weights.items()}


def minimum_variance(candidates: list[dict],
                      price_data: dict[str, pd.Series] | None = None,
                      **kw) -> dict[str, float]:
    """Min-variance long-only portfolio via quadratic programming."""
    if price_data is None:
        return equal_weight(candidates)
    R = _returns_matrix(candidates, price_data)
    if R.empty or R.shape[1] < 2:
        return equal_weight(candidates)

    from scipy.optimize import minimize
    cov = R.cov().values * 252
    n = cov.shape[0]

    def objective(w):
        return float(w @ cov @ w)

    x0 = np.ones(n) / n
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(objective, x0, method="SLSQP", bounds=bounds,
                   constraints=constraints, options={"maxiter": 200})
    if not res.success:
        return equal_weight(candidates)
    return dict(zip(R.columns.tolist(), [float(x) for x in res.x]))


def maximum_diversification(candidates: list[dict],
                              price_data: dict[str, pd.Series] | None = None,
                              **kw) -> dict[str, float]:
    """Max Diversification Ratio (Choueifaty-Coignard) — maximise
    (w·σ) / sqrt(w·Σ·w). Long-only, sum-to-1."""
    if price_data is None:
        return equal_weight(candidates)
    R = _returns_matrix(candidates, price_data)
    if R.empty or R.shape[1] < 2:
        return equal_weight(candidates)

    from scipy.optimize import minimize
    cov = R.cov().values * 252
    sigma = np.sqrt(np.diag(cov))
    n = cov.shape[0]

    def negative_dr(w):
        num = float(w @ sigma)
        den = math.sqrt(float(w @ cov @ w))
        if den == 0:
            return 0.0
        return -num / den

    x0 = np.ones(n) / n
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(negative_dr, x0, method="SLSQP", bounds=bounds,
                   constraints=constraints, options={"maxiter": 200})
    if not res.success:
        return equal_weight(candidates)
    return dict(zip(R.columns.tolist(), [float(x) for x in res.x]))


def maximum_sharpe(candidates: list[dict],
                    price_data: dict[str, pd.Series] | None = None,
                    rf: float = 0.05, **kw) -> dict[str, float]:
    """Tangency portfolio (max Sharpe) using historical returns as expected returns.

    WARNING: known to be unstable on noisy inputs. Use with a stability cap.
    """
    if price_data is None:
        return equal_weight(candidates)
    R = _returns_matrix(candidates, price_data)
    if R.empty or R.shape[1] < 2:
        return equal_weight(candidates)

    from scipy.optimize import minimize
    mu = R.mean() * 252
    cov = R.cov().values * 252
    n = cov.shape[0]

    def negative_sharpe(w):
        port_ret = float(w @ mu.values)
        port_vol = math.sqrt(float(w @ cov @ w))
        if port_vol <= 0:
            return 0.0
        return -(port_ret - rf) / port_vol

    x0 = np.ones(n) / n
    bounds = [(0.0, 0.3)] * n                                           # 30% cap for stability
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(negative_sharpe, x0, method="SLSQP", bounds=bounds,
                   constraints=constraints, options={"maxiter": 200})
    if not res.success:
        return equal_weight(candidates)
    return dict(zip(R.columns.tolist(), [float(x) for x in res.x]))


def kelly_fraction(candidates: list[dict],
                    price_data: dict[str, pd.Series] | None = None,
                    fraction: float = 0.25, **kw) -> dict[str, float]:
    """Fractional Kelly. Uses mean/vol as edge estimate. Clamped."""
    if price_data is None:
        return equal_weight(candidates)
    R = _returns_matrix(candidates, price_data)
    if R.empty or R.shape[1] < 2:
        return equal_weight(candidates)

    mu = R.mean() * 252
    vol_sq = R.var() * 252
    # Kelly per-stock: mu / vol^2 (unlevered). Take fractional and normalise long-only.
    kelly = mu / vol_sq
    kelly = kelly.clip(lower=0.0)                                      # long-only
    if kelly.sum() == 0:
        return equal_weight(candidates)
    weights = kelly * fraction / kelly.sum()
    # Sum-to-1 (fractional Kelly leaves cash otherwise — for portfolio purposes normalise)
    return {t: float(w / weights.sum()) for t, w in weights.items() if w > 0}


# ── Registry ─────────────────────────────────────────────────────────────────

ALLOCATORS: dict[str, Callable[..., dict[str, float]]] = {
    "equal":              equal_weight,
    "score":              score_weight,
    "confidence":         confidence_weight,
    "score_x_confidence": score_x_confidence_weight,
    "inverse_vol":        inverse_volatility_weight,
    "volatility":         volatility_weight,
    "hrp":                hierarchical_risk_parity,
    "min_variance":       minimum_variance,
    "max_diversification": maximum_diversification,
    "max_sharpe":         maximum_sharpe,
    "kelly_quarter":      lambda *a, **kw: kelly_fraction(*a, fraction=0.25, **kw),
}
