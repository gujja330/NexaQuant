"""Earnings features from CanonicalEarnings rows."""
from __future__ import annotations

from datetime import date

from backend.canonical.schemas import CanonicalDataset


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    earn = canon.get("earnings")
    if not earn or not earn.rows:
        return out
    for e in earn.rows:
        if e.symbol not in universe:
            continue
        days = None
        if e.next_earnings_date is not None and asof is not None:
            days = (e.next_earnings_date - asof).days
        out[e.symbol] = {
            "earn_days_to_next":         days,
            "earn_last_surprise_pct":    e.last_surprise_pct,
            "earn_last_eps_reported":    e.last_reported_eps,
            "earn_last_eps_estimate":    e.last_eps_estimate,
        }
    return out
