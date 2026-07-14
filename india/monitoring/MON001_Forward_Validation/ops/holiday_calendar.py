"""
NSE trading calendar for MON001 operational layer.

Mirrors the set used by scripts/check_data_freshness.py so weekend/holiday handling is
consistent across the pipeline. Read-only utilities.
"""
from __future__ import annotations

from datetime import date, timedelta


# Hand-curated NSE holidays. Keep in sync with scripts/check_data_freshness.py.
# Missing an obscure holiday is tolerated: the freshness gate absorbs a single missed
# session; MON001 daily runner treats an unrecognized holiday as a "possibly stale" day
# rather than an error.
NSE_HOLIDAYS: set[date] = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 6),    # Holi
    date(2026, 3, 31),   # Id-Ul-Fitr
    date(2026, 4, 3),    # Mahavir Jayanti
    date(2026, 4, 10),   # Good Friday
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 11, 8),   # Diwali (muhurat)
    date(2026, 11, 25),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
    # 2027 (partial — add as calendar publishes)
    date(2027, 1, 26),
    date(2027, 3, 25),
    date(2027, 3, 30),
    date(2027, 4, 2),
    date(2027, 5, 1),
    date(2027, 8, 15),
    date(2027, 10, 2),
    date(2027, 12, 25),
}


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_holiday(d: date) -> bool:
    return d in NSE_HOLIDAYS


def is_trading_day(d: date) -> bool:
    return not is_weekend(d) and not is_holiday(d)


def previous_trading_day(d: date | None = None) -> date:
    d = (d or date.today()) - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d: date | None = None) -> date:
    d = (d or date.today()) + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def trading_days_between(start: date, end: date) -> int:
    """Count trading days in (start, end]. Both bounds inclusive on the trading-day count."""
    if end < start:
        return 0
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n
