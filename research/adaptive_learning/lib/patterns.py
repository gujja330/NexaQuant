"""DEV025 pattern discovery.

Statistical mining of the trade history for repeated winning/losing patterns:
  - Best/worst sectors by hit-rate
  - Best/worst industries
  - Score-bucket accuracy
  - Dimension-value → outcome correlations
  - Regime-conditional performance (once regime data is available in future)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def score_bucket_accuracy(trades: pd.DataFrame,
                            bin_edges: list[float] | None = None) -> pd.DataFrame:
    """Group trades by score bucket; measure win rate + avg return per bucket."""
    if trades.empty:
        return pd.DataFrame()
    edges = bin_edges or [0, 40, 50, 55, 60, 65, 70, 75, 80, 90, 100]
    df = trades.copy()
    df["score_bucket"] = pd.cut(df["score_at_entry"], bins=edges, include_lowest=True)
    rows = []
    for bucket, g in df.groupby("score_bucket", observed=True):
        if len(g) == 0:
            continue
        rows.append({
            "score_bucket":       str(bucket),
            "n_trades":           int(len(g)),
            "win_rate_pct":       round(float(g["is_winner"].mean()) * 100, 2),
            "avg_return_pct":     round(float(g["return_pct"].mean()), 3),
            "median_return_pct":  round(float(g["return_pct"].median()), 3),
            "avg_mfe_pct":        round(float(g["mfe_pct"].mean()), 3),
            "avg_mae_pct":        round(float(g["mae_pct"].mean()), 3),
            "5pct_target_rate":   round(float(g["hit_5pct_target"].mean()) * 100, 2),
            "5pct_stop_rate":     round(float(g["hit_5pct_stop"].mean()) * 100, 2),
        })
    return pd.DataFrame(rows).sort_values("score_bucket")


def per_sector_performance(trades: pd.DataFrame, min_n: int = 20) -> pd.DataFrame:
    if trades.empty or "sector" not in trades.columns:
        return pd.DataFrame()
    rows = []
    for sec, g in trades.groupby("sector"):
        if len(g) < min_n:
            continue
        rows.append({
            "sector":            sec,
            "n_trades":          int(len(g)),
            "win_rate_pct":      round(float(g["is_winner"].mean()) * 100, 2),
            "avg_return_pct":    round(float(g["return_pct"].mean()), 3),
            "avg_score":         round(float(g["score_at_entry"].mean()), 2),
            "avg_conf":          round(float(g["confidence"].mean()), 3),
        })
    return pd.DataFrame(rows).sort_values("avg_return_pct", ascending=False)


def per_industry_performance(trades: pd.DataFrame, min_n: int = 15) -> pd.DataFrame:
    if trades.empty or "industry" not in trades.columns:
        return pd.DataFrame()
    rows = []
    for ind, g in trades.groupby("industry"):
        if len(g) < min_n:
            continue
        rows.append({
            "industry":         ind,
            "n_trades":         int(len(g)),
            "win_rate_pct":     round(float(g["is_winner"].mean()) * 100, 2),
            "avg_return_pct":   round(float(g["return_pct"].mean()), 3),
        })
    return pd.DataFrame(rows).sort_values("avg_return_pct", ascending=False)


def dimension_correlations(trades: pd.DataFrame) -> pd.DataFrame:
    """Correlate each PIT dimension value at entry with realised return."""
    if trades.empty:
        return pd.DataFrame()
    dim_cols = [c for c in trades.columns if c.startswith("dim_")]
    rows = []
    for col in dim_cols:
        sub = trades[[col, "return_pct"]].dropna()
        if len(sub) < 30:
            continue
        corr = float(sub[col].corr(sub["return_pct"]))
        rows.append({
            "dimension":               col,
            "spearman_correlation":    round(float(sub[col].corr(sub["return_pct"], method="spearman")), 4),
            "pearson_correlation":     round(corr, 4),
            "n_trades":                int(len(sub)),
            "avg_return_top_quintile": round(float(
                sub.nlargest(len(sub) // 5, col)["return_pct"].mean()), 3),
            "avg_return_bot_quintile": round(float(
                sub.nsmallest(len(sub) // 5, col)["return_pct"].mean()), 3),
        })
    return pd.DataFrame(rows).sort_values("spearman_correlation", ascending=False)


def stop_loss_effectiveness(trades: pd.DataFrame) -> dict:
    """Would tighter/looser stops have improved outcomes?"""
    if trades.empty:
        return {}
    stopped_5pct = trades[trades["hit_5pct_stop"]]
    total = len(trades)
    return {
        "n_trades":                    total,
        "hit_5pct_stop_rate":          round(len(stopped_5pct) / total * 100, 2),
        "hit_5pct_stop_avg_final_ret": round(float(stopped_5pct["return_pct"].mean()), 3)
                                          if not stopped_5pct.empty else None,
        "hit_5pct_stop_median_final":  round(float(stopped_5pct["return_pct"].median()), 3)
                                          if not stopped_5pct.empty else None,
        "hit_10pct_stop_rate":         round(float(trades["hit_10pct_stop"].mean()) * 100, 2),
        "final_win_rate_among_5pct_dippers":
            round(float(stopped_5pct["is_winner"].mean()) * 100, 2)
            if not stopped_5pct.empty else None,
    }


def target_effectiveness(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    hit_5pct_gainers = trades[trades["hit_5pct_target"]]
    hit_10pct_gainers = trades[trades["hit_10pct_target"]]
    total = len(trades)
    return {
        "hit_5pct_target_rate":     round(len(hit_5pct_gainers) / total * 100, 2),
        "hit_5pct_avg_final_ret":   round(float(hit_5pct_gainers["return_pct"].mean()), 3)
                                       if not hit_5pct_gainers.empty else None,
        "hit_10pct_target_rate":    round(len(hit_10pct_gainers) / total * 100, 2),
        "hit_10pct_avg_final_ret":  round(float(hit_10pct_gainers["return_pct"].mean()), 3)
                                       if not hit_10pct_gainers.empty else None,
    }
