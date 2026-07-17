"""DEV030 · pairwise head-to-head matrix between strategies."""
from __future__ import annotations

import numpy as np
import pandas as pd


METRICS = [
    ("sharpe_ratio",       "sharpe"),
    ("sortino_ratio",      "sortino"),
    ("calmar_ratio",       "calmar"),
    ("cagr",               "cagr"),
    ("max_dd_pct",         "max_dd"),
    ("information_ratio",  "info_ratio"),
    ("win_rate",           "win_rate"),
]


def _get(row: pd.Series, keys: list[str]):
    for k in keys:
        if k in row.index and row[k] is not None:
            v = row[k]
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                continue
            return v
    return None


def build_matrix(scored: pd.DataFrame) -> list[dict]:
    """Return upper-triangular list of pairwise deltas.

    Each entry: {a, b, delta_sharpe, delta_return, delta_dd, winner_by_composite}."""
    if scored.empty or len(scored) < 2:
        return []
    strat_col = "strategy" if "strategy" in scored.columns else scored.columns[0]
    pairs = []
    n = len(scored)
    for i in range(n):
        for j in range(i + 1, n):
            a = scored.iloc[i]
            b = scored.iloc[j]
            delta = {}
            for canonical, short in [("sharpe_ratio", "sharpe"),
                                       ("sortino_ratio", "sortino"),
                                       ("calmar_ratio", "calmar"),
                                       ("cagr", "cagr"),
                                       ("max_dd_pct", "max_dd"),
                                       ("information_ratio", "info_ratio"),
                                       ("win_rate", "win_rate")]:
                va = _get(a, [canonical])
                vb = _get(b, [canonical])
                if va is not None and vb is not None:
                    delta[f"delta_{short}"] = round(float(va) - float(vb), 4)
            winner = a[strat_col] if a["composite_score"] >= b["composite_score"] else b[strat_col]
            pairs.append({
                "a":                   str(a[strat_col]),
                "b":                   str(b[strat_col]),
                "composite_a":         float(a["composite_score"]),
                "composite_b":         float(b["composite_score"]),
                "winner_by_composite": str(winner),
                **delta,
            })
    return pairs
