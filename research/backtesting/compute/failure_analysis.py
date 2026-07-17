"""Failure analysis for DEV021.

Detects and reports:
  - Worst 10 trades (largest per-trade losses)
  - Worst 5 months (largest monthly drawdowns)
  - Drawdown periods ranked by depth
  - Consecutive-loss streaks
  - Weakest sectors and industries
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "research"))
from company_intelligence.lib import company_catalog                                # noqa: E402


def _sector_of(ticker: str) -> str:
    try:
        return company_catalog.by_ticker(ticker).parent_sector_display
    except KeyError:
        return "Unknown"


def worst_trades(trade_log: list[dict], n: int = 10) -> list[dict]:
    if not trade_log:
        return []
    sorted_asc = sorted(trade_log, key=lambda t: t["return_pct"])
    out = []
    for t in sorted_asc[:n]:
        out.append({
            "rebal_date":   t["rebal_date"],
            "next_date":    t["next_date"],
            "ticker":       t["ticker"],
            "sector":       _sector_of(t["ticker"]),
            "weight":       round(t["weight"], 4),
            "return_pct":   round(t["return_pct"], 2),
            "entry_px":     round(t["entry_px"], 2),
            "exit_px":      round(t["exit_px"], 2),
        })
    return out


def best_trades(trade_log: list[dict], n: int = 10) -> list[dict]:
    if not trade_log:
        return []
    sorted_desc = sorted(trade_log, key=lambda t: t["return_pct"], reverse=True)
    out = []
    for t in sorted_desc[:n]:
        out.append({
            "rebal_date":   t["rebal_date"],
            "next_date":    t["next_date"],
            "ticker":       t["ticker"],
            "sector":       _sector_of(t["ticker"]),
            "weight":       round(t["weight"], 4),
            "return_pct":   round(t["return_pct"], 2),
            "entry_px":     round(t["entry_px"], 2),
            "exit_px":      round(t["exit_px"], 2),
        })
    return out


def worst_months(daily_returns: pd.Series, n: int = 5) -> list[dict]:
    if daily_returns.empty:
        return []
    monthly = (1 + daily_returns).resample("ME").prod() - 1
    monthly = monthly.dropna()
    sorted_asc = monthly.sort_values().head(n)
    return [{"month": ts.strftime("%Y-%m"),
             "return_pct": round(float(v) * 100, 2)}
            for ts, v in sorted_asc.items()]


def best_months(daily_returns: pd.Series, n: int = 5) -> list[dict]:
    if daily_returns.empty:
        return []
    monthly = (1 + daily_returns).resample("ME").prod() - 1
    monthly = monthly.dropna()
    sorted_desc = monthly.sort_values(ascending=False).head(n)
    return [{"month": ts.strftime("%Y-%m"),
             "return_pct": round(float(v) * 100, 2)}
            for ts, v in sorted_desc.items()]


def drawdown_periods(daily_returns: pd.Series, top_n: int = 5, min_dd_pct: float = -3.0) -> list[dict]:
    """Identify distinct drawdown episodes ranked by depth."""
    if daily_returns.empty:
        return []
    equity = (1 + daily_returns).cumprod()
    peak = equity.cummax()
    dd = (equity / peak - 1) * 100

    in_dd = dd < min_dd_pct
    episodes = []
    start = None
    for dt, flag in in_dd.items():
        if flag and start is None:
            start = dt
        elif not flag and start is not None:
            trough = dd.loc[start:dt].idxmin()
            depth = float(dd.loc[start:dt].min())
            episodes.append({"start": start, "trough": trough, "end": dt,
                              "depth_pct": depth,
                              "duration_days": int((dt - start).days)})
            start = None
    if start is not None:                                                # unfinished DD at end
        trough = dd.loc[start:].idxmin()
        depth = float(dd.loc[start:].min())
        episodes.append({"start": start, "trough": trough, "end": None,
                          "depth_pct": depth,
                          "duration_days": int((dd.index[-1] - start).days)})

    episodes.sort(key=lambda e: e["depth_pct"])
    top = episodes[:top_n]
    return [{"start":         e["start"].strftime("%Y-%m-%d"),
             "trough":        e["trough"].strftime("%Y-%m-%d"),
             "end":           e["end"].strftime("%Y-%m-%d") if e["end"] else "ongoing",
             "depth_pct":     round(e["depth_pct"], 2),
             "duration_days": e["duration_days"]}
            for e in top]


def analyse_failures(daily_returns: pd.Series, trade_log: list[dict]) -> dict:
    return {
        "worst_10_trades":     worst_trades(trade_log, 10),
        "best_10_trades":      best_trades(trade_log, 10),
        "worst_5_months":      worst_months(daily_returns, 5),
        "best_5_months":       best_months(daily_returns, 5),
        "top_5_drawdown_episodes": drawdown_periods(daily_returns, top_n=5),
    }
