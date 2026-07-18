"""Validation Engine v2.0 · opportunity cost tracking.

For every ticker NOT recommended today that would have won by a look-ahead
window, log the missed edge. The report answers: how much did our
abstention discipline cost us?"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]


def compute_opportunity_cost(recommendations: dict,
                                  learning: pd.DataFrame,
                                  window_days: int = 30) -> dict:
    """Given today's rec set + trade history, identify tickers with
    winning history that we did NOT recommend this cycle.

    This is a directional measure — it does not claim we would have
    predicted them; it only quantifies what the discipline gave up."""
    if learning.empty:
        return {"note": "no learning history", "n_missed": 0}

    rec_by_ticker = {str(r["ticker"]): r for r in (recommendations.get("recommendations") or [])}

    # For each ticker in the recent window, compute realised win rate + expectancy
    df = learning.copy()
    df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
    if df["exit_date"].isna().all():
        return {"note": "no valid exit dates", "n_missed": 0}
    recent_cutoff = df["exit_date"].max() - pd.Timedelta(days=window_days)
    recent = df[df["exit_date"] >= recent_cutoff]
    if recent.empty:
        return {"note": "no recent trades", "n_missed": 0}

    by_ticker = recent.groupby("ticker").agg(
        n_trades=("is_winner", "count"),
        win_rate=("is_winner", "mean"),
        expectancy=("return_pct", "mean"),
    ).reset_index()

    # Missed = ticker with win_rate >= 0.65 and expectancy > 0 but NOT
    # currently recommended as Buy / Strong-Buy / Accumulate.
    strong_positions = {"Strong-Buy", "Buy", "Accumulate"}
    def _is_recommended(t: str) -> bool:
        r = rec_by_ticker.get(t)
        return bool(r and r.get("recommendation") in strong_positions)

    missed = by_ticker[
        (by_ticker["win_rate"] >= 0.65)
        & (by_ticker["expectancy"] > 0)
        & (~by_ticker["ticker"].apply(_is_recommended))
    ].copy()
    missed = missed.sort_values("expectancy", ascending=False)

    total_missed_expectancy = float(missed["expectancy"].sum())
    return {
        "window_days":            window_days,
        "n_tickers_in_window":    int(len(by_ticker)),
        "n_missed_edges":         int(len(missed)),
        "total_missed_expectancy": round(total_missed_expectancy, 4),
        "avg_missed_expectancy":  round(float(missed["expectancy"].mean()), 4) if len(missed) else 0.0,
        "top_missed":             missed.head(10).to_dict(orient="records"),
    }
