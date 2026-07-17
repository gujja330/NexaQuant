"""DEV025 confidence calibration analysis.

Given a per-trade dataframe with (confidence, is_winner, return_pct),
compute:
  - Reliability diagram (predicted confidence vs actual win rate)
  - Brier score
  - Expected Calibration Error (ECE)
  - Over/under-confidence flags per sector
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calibration_curve(trades: pd.DataFrame,
                        n_bins: int = 10,
                        confidence_col: str = "confidence",
                        outcome_col: str = "is_winner") -> pd.DataFrame:
    """Bin trades by predicted confidence, compute empirical win rate per bin."""
    if trades.empty:
        return pd.DataFrame()

    df = trades[[confidence_col, outcome_col]].dropna().copy()
    if df.empty:
        return pd.DataFrame()

    df["bin"] = pd.cut(df[confidence_col], bins=n_bins, include_lowest=True)
    rows = []
    for bin_label, g in df.groupby("bin", observed=True):
        rows.append({
            "confidence_bin":    str(bin_label),
            "bin_midpoint":      round(float(bin_label.mid), 3),
            "n_trades":          int(len(g)),
            "predicted_conf":    round(float(g[confidence_col].mean()), 4),
            "actual_win_rate":   round(float(g[outcome_col].mean()), 4),
            "calibration_gap":   round(float(g[outcome_col].mean() - g[confidence_col].mean()), 4),
        })
    return pd.DataFrame(rows).sort_values("bin_midpoint")


def brier_score(trades: pd.DataFrame,
                 confidence_col: str = "confidence",
                 outcome_col: str = "is_winner") -> float:
    """Brier score = mean((predicted - actual)²). Lower is better."""
    if trades.empty:
        return float("nan")
    df = trades[[confidence_col, outcome_col]].dropna()
    if df.empty:
        return float("nan")
    predicted = df[confidence_col].astype(float).values
    actual = df[outcome_col].astype(float).values
    return float(np.mean((predicted - actual) ** 2))


def expected_calibration_error(curve_df: pd.DataFrame) -> float:
    """ECE: weighted average of |predicted - actual| across bins."""
    if curve_df.empty:
        return float("nan")
    total = curve_df["n_trades"].sum()
    if total == 0:
        return float("nan")
    weighted = ((curve_df["predicted_conf"] - curve_df["actual_win_rate"]).abs()
                  * curve_df["n_trades"]).sum()
    return float(weighted / total)


def per_sector_calibration(trades: pd.DataFrame,
                             confidence_col: str = "confidence",
                             outcome_col: str = "is_winner") -> pd.DataFrame:
    """For each sector: mean predicted vs mean actual — flag over/under-confidence."""
    if trades.empty or "sector" not in trades.columns:
        return pd.DataFrame()

    df = trades[[confidence_col, outcome_col, "sector"]].dropna(subset=[confidence_col])
    rows = []
    for sec, g in df.groupby("sector"):
        if len(g) < 10:                                # insufficient sample
            continue
        pred = float(g[confidence_col].mean())
        actual = float(g[outcome_col].mean())
        gap = actual - pred
        flag = "well_calibrated"
        if gap > 0.05:
            flag = "under_confident"
        elif gap < -0.05:
            flag = "over_confident"
        rows.append({
            "sector":          sec,
            "n_trades":        int(len(g)),
            "predicted_conf":  round(pred, 4),
            "actual_win_rate": round(actual, 4),
            "gap":             round(gap, 4),
            "flag":            flag,
        })
    return pd.DataFrame(rows).sort_values("gap")
