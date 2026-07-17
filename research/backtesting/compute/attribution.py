"""Sector / signal attribution for DEV021.

Given a trade log with tickers and returns, aggregate the P&L contribution by:
  - Parent sector (via DEV019 industry catalog → parent_sector)
  - Parent industry
  - Score bucket (top-quintile score vs bottom-quintile)

For v0.1 this is TRADE-LEVEL attribution, not portfolio-level factor decomposition.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "research"))
from company_intelligence.lib import company_catalog                                # noqa: E402


def _lookup(ticker: str) -> tuple[str, str]:
    """Return (sector_display, industry_display) or ('Unknown', 'Unknown')."""
    try:
        c = company_catalog.by_ticker(ticker)
        return c.parent_sector_display, c.industry_display
    except KeyError:
        return "Unknown", "Unknown"


def attribute_trades(trade_log: list[dict]) -> dict:
    """Compute per-sector and per-industry cumulative P&L contribution."""
    sector_pnl: dict = defaultdict(lambda: {"n": 0, "sum_ret": 0.0, "sum_weighted": 0.0})
    industry_pnl: dict = defaultdict(lambda: {"n": 0, "sum_ret": 0.0, "sum_weighted": 0.0})

    for trade in trade_log:
        sec, ind = _lookup(trade["ticker"])
        ret = trade["return_pct"]
        w = trade["weight"]
        weighted = ret * w

        sector_pnl[sec]["n"] += 1
        sector_pnl[sec]["sum_ret"] += ret
        sector_pnl[sec]["sum_weighted"] += weighted

        industry_pnl[ind]["n"] += 1
        industry_pnl[ind]["sum_ret"] += ret
        industry_pnl[ind]["sum_weighted"] += weighted

    # Convert to sorted lists with averages
    def _rank(d: dict) -> list[dict]:
        rows = []
        for k, v in d.items():
            avg_ret = v["sum_ret"] / v["n"] if v["n"] > 0 else 0.0
            rows.append({
                "name":                  k,
                "n_trades":              v["n"],
                "avg_trade_return_pct":  round(avg_ret, 3),
                "cumulative_contribution_pct": round(v["sum_weighted"], 3),
                "win_rate_pct":          None,  # populated below
            })
        rows.sort(key=lambda r: r["cumulative_contribution_pct"], reverse=True)
        return rows

    # Win rates (secondary pass)
    sec_win: dict = defaultdict(lambda: {"win": 0, "total": 0})
    ind_win: dict = defaultdict(lambda: {"win": 0, "total": 0})
    for trade in trade_log:
        sec, ind = _lookup(trade["ticker"])
        sec_win[sec]["total"] += 1
        ind_win[ind]["total"] += 1
        if trade["return_pct"] > 0:
            sec_win[sec]["win"] += 1
            ind_win[ind]["win"] += 1

    sector_rows = _rank(sector_pnl)
    for r in sector_rows:
        w = sec_win[r["name"]]
        r["win_rate_pct"] = round(w["win"] / w["total"] * 100, 1) if w["total"] > 0 else None

    industry_rows = _rank(industry_pnl)
    for r in industry_rows:
        w = ind_win[r["name"]]
        r["win_rate_pct"] = round(w["win"] / w["total"] * 100, 1) if w["total"] > 0 else None

    return {
        "by_sector":   sector_rows,
        "by_industry": industry_rows,
    }
