"""Fundamentals · Layer 5 · Event / Governance (2 signals)

Earnings-calendar window · Promoter pledge % (India-only governance signal).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def earnings_calendar_window(fin: dict, asof: str) -> Optional[int]:
    """Trading-days-to-next-earnings from asof (0 = today, -1 = unknown).

    Uses calendar days as a proxy · caller can convert to trading days.
    fin["next_earnings_date"] · ISO date string.
    """
    v = fin.get("next_earnings_date")
    if not v:
        return -1
    try:
        d1 = datetime.fromisoformat(str(v)).date()
        d0 = datetime.fromisoformat(str(asof)).date()
        delta = (d1 - d0).days
        return int(delta)
    except (TypeError, ValueError):
        return -1


def promoter_pledge_pct(fin: dict, market: str) -> Optional[float]:
    """India-only · pledged_shares / promoter_holding.

    USA returns None. High pledge % is a governance red-flag.
    """
    if market != "india":
        return None
    for k in ("promoter_pledged_shares", "promoter_total_shares"):
        if k not in fin or fin[k] is None:
            return None
    try:
        total = float(fin["promoter_total_shares"])
        if total <= 0: return None
        return round(float(fin["promoter_pledged_shares"]) / total, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


LAYER5_FUNCTIONS = {
    "earnings_calendar_window": earnings_calendar_window,
    "promoter_pledge_pct":      promoter_pledge_pct,
}
