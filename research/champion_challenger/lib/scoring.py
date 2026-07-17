"""DEV030 · composite scoring for strategies.

The composite score is a weighted combination of risk-adjusted return metrics
plus quality-of-execution metrics. All weights are transparent constants; no
manual tuning during a run.

Every metric is normalized to a [0, 100] scale via min-max within the strategy
universe so the composite is scale-free."""
from __future__ import annotations

import numpy as np
import pandas as pd


# ── weights (must sum to 1.0) ─────────────────────────────────────────────
WEIGHTS = {
    "sharpe":     0.25,
    "sortino":    0.15,
    "calmar":     0.15,
    "info_ratio": 0.10,
    "cagr":       0.10,
    "max_dd":     0.10,   # LOWER is better — inverted below
    "win_rate":   0.05,
    "profit_factor": 0.05,
    "expectancy": 0.05,
}

# Direction: +1 = higher-better, -1 = lower-better
DIRECTION = {
    "sharpe":     +1,
    "sortino":    +1,
    "calmar":     +1,
    "info_ratio": +1,
    "cagr":       +1,
    "max_dd":     -1,     # max_dd_pct is negative-loss; we invert
    "win_rate":   +1,
    "profit_factor": +1,
    "expectancy": +1,
}


def _minmax(values: np.ndarray, direction: int) -> np.ndarray:
    """Return [0, 100] scaled values. NaN -> 0. Direction -1 flips."""
    v = np.asarray(values, dtype=float)
    finite = np.isfinite(v)
    if not finite.any():
        return np.zeros_like(v)
    lo, hi = np.nanmin(v[finite]), np.nanmax(v[finite])
    if hi == lo:
        out = np.where(finite, 50.0, 0.0)
        return out
    scaled = (v - lo) / (hi - lo) * 100.0
    if direction == -1:
        scaled = 100.0 - scaled
    scaled = np.where(finite, scaled, 0.0)
    return scaled


def _pick(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """First existing column matching any candidate name."""
    for name in candidates:
        if name in df.columns:
            return name
    return None


# Column name resolvers (DEV021 uses annual_vol/max_dd_pct etc.)
COL_MAP = {
    "sharpe":     ["sharpe_ratio", "sharpe"],
    "sortino":    ["sortino_ratio", "sortino"],
    "calmar":     ["calmar_ratio", "calmar"],
    "info_ratio": ["information_ratio", "info_ratio"],
    "cagr":       ["cagr"],
    "max_dd":     ["max_dd_pct", "max_drawdown_pct"],
    "win_rate":   ["win_rate", "win_rate_pct", "trade_win_rate"],
    "profit_factor": ["profit_factor"],
    "expectancy": ["expectancy", "expectancy_pct"],
}


def score_strategies(strategies: pd.DataFrame) -> pd.DataFrame:
    """Return `strategies` with `composite_score` and per-metric normalised columns."""
    if strategies.empty:
        return strategies

    out = strategies.copy().reset_index(drop=True)

    composite = np.zeros(len(out), dtype=float)
    weight_used_total = 0.0
    per_metric_norm = {}

    for metric, weight in WEIGHTS.items():
        col = _pick(out, COL_MAP[metric])
        if col is None:
            continue
        raw = out[col].values
        norm = _minmax(raw, DIRECTION[metric])
        per_metric_norm[f"norm_{metric}"] = norm
        composite += weight * norm
        weight_used_total += weight

    if weight_used_total > 0:
        composite = composite / weight_used_total

    out["composite_score"] = np.round(composite, 3)
    for k, v in per_metric_norm.items():
        out[k] = np.round(v, 2)

    out = out.sort_values("composite_score", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def rank_summary(scored: pd.DataFrame) -> list[dict]:
    """Compact leaderboard rows for JSON export."""
    if scored.empty:
        return []
    strat_col = "strategy" if "strategy" in scored.columns else scored.columns[0]

    def _get(row, keys, default=None):
        for k in keys:
            if k in row and row[k] is not None:
                v = row[k]
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    continue
                return v
        return default

    rows = []
    for _, row in scored.iterrows():
        rows.append({
            "rank":            int(row["rank"]),
            "strategy":        str(row[strat_col]),
            "composite_score": float(row["composite_score"]),
            "sharpe":          _get(row, ["sharpe_ratio", "sharpe"]),
            "sortino":         _get(row, ["sortino_ratio", "sortino"]),
            "calmar":          _get(row, ["calmar_ratio", "calmar"]),
            "cagr":            _get(row, ["cagr"]),
            "max_dd_pct":      _get(row, ["max_dd_pct", "max_drawdown_pct"]),
            "info_ratio":      _get(row, ["information_ratio", "info_ratio"]),
            "win_rate":        _get(row, ["win_rate", "win_rate_pct", "trade_win_rate"]),
            "profit_factor":   _get(row, ["profit_factor"]),
            "expectancy":      _get(row, ["expectancy", "expectancy_pct"]),
        })
    return rows
