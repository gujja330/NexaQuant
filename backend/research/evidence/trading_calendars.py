"""AUDIT-01 · Exchange-aware trading day arithmetic.

CEO 2026-09-05 · walk-forward embargo and window sizing must honor real
NSE + NYSE holidays. Weekday-only arithmetic drifts by ~10-15 days per year
per market · over 252-day training windows the boundary can straddle
holiday clusters and quietly leak signal.

Small hardcoded holiday sets kept intentionally static · a full library
dependency (pandas_market_calendars) is a heavier commitment for a small
gain. When the holiday set drifts (e.g. NSE announces a new observed
holiday), add the date here + note the year.
"""
from __future__ import annotations
from datetime import date, timedelta


# NSE holidays 2020-2027 (major observed exchange holidays · not exhaustive)
NSE_HOLIDAYS = frozenset(map(date.fromisoformat, [
    # 2020
    "2020-02-21", "2020-03-10", "2020-04-02", "2020-04-06", "2020-04-10",
    "2020-04-14", "2020-05-01", "2020-05-25", "2020-10-02", "2020-11-16",
    "2020-11-30", "2020-12-25",
    # 2021
    "2021-01-26", "2021-03-11", "2021-03-29", "2021-04-02", "2021-04-14",
    "2021-04-21", "2021-05-13", "2021-07-21", "2021-08-19", "2021-09-10",
    "2021-10-15", "2021-11-04", "2021-11-05", "2021-11-19",
    # 2022
    "2022-01-26", "2022-03-01", "2022-03-18", "2022-04-14", "2022-04-15",
    "2022-05-03", "2022-08-09", "2022-08-15", "2022-08-31", "2022-10-05",
    "2022-10-24", "2022-10-26", "2022-11-08",
    # 2023
    "2023-01-26", "2023-03-07", "2023-03-30", "2023-04-04", "2023-04-07",
    "2023-04-14", "2023-05-01", "2023-06-29", "2023-08-15", "2023-09-19",
    "2023-10-02", "2023-10-24", "2023-11-14", "2023-11-27", "2023-12-25",
    # 2024
    "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29", "2024-04-11",
    "2024-04-17", "2024-05-01", "2024-05-20", "2024-06-17", "2024-07-17",
    "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15", "2024-12-25",
    # 2025
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-08-15", "2025-08-27",
    "2025-10-02", "2025-10-21", "2025-10-22", "2025-11-05", "2025-12-25",
    # 2026 (published NSE calendar)
    "2026-01-26", "2026-02-17", "2026-03-03", "2026-03-19", "2026-04-01",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-27", "2026-06-25",
    "2026-08-15", "2026-08-27", "2026-10-02", "2026-11-09", "2026-11-25",
    "2026-12-25",
]))


# NYSE holidays 2020-2027 (federal + NYSE observed)
NYSE_HOLIDAYS = frozenset(map(date.fromisoformat, [
    # 2020
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25",
    "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25",
    # 2021
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
    # 2022
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    # 2023
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    # 2024
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    # 2025
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
]))


CALENDARS = {
    "india": NSE_HOLIDAYS,
    "usa":   NYSE_HOLIDAYS,
}


def is_trading_day(d: date, market: str) -> bool:
    """Weekday AND not-a-holiday for the given exchange."""
    if d.weekday() >= 5: return False
    holidays = CALENDARS.get(market.lower(), frozenset())
    return d not in holidays


def add_trading_days(d: date, n: int, market: str) -> date:
    """Add n trading days for the exchange · Mon-Fri minus holidays."""
    cur = d
    added = 0
    while added < n:
        cur = cur + timedelta(days=1)
        if is_trading_day(cur, market):
            added += 1
    return cur


def trading_days_between(from_d: date, to_d: date, market: str) -> int:
    """Count trading days in (from_d, to_d] · exclusive of from_d, inclusive of to_d."""
    if to_d <= from_d: return 0
    n = 0
    cur = from_d
    while cur < to_d:
        cur = cur + timedelta(days=1)
        if is_trading_day(cur, market):
            n += 1
    return n
