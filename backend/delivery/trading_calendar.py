"""AEGIS · Delivery · Canonical Trading Calendar.

CEO handover 2026-08-27 (post-I26/I28 architecture directive):
> "Make exit dates derived, never manually inferred.
>  exit_date must satisfy:
>    prediction_date < entry_date <= exit_date
>    exit_date ∈ canonical trading calendar
>    exit_date <= evaluation/as-of date
>  For a 5D outcome: exit_date = the 5th valid trading session after entry_date.
>  Not: entry_date + 5 calendar days."

Read-only calendar derived from the per-market index parquet(s):
   India · data/raw/india/NSEI_D1.parquet
   USA   · usa/data/raw/us/_IDX_GSPC_D1.parquet (or SPY_D1.parquet fallback)

Deliberately dependency-free · pandas + pathlib only · no external
calendar library. That keeps the calendar authoritatively equal to the
data we already have.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


INDEX_PATHS = {
    "india": ("data/raw/india/NSEI_D1.parquet",
              "data/raw/india/NIFTY_D1.parquet"),
    "usa":   ("usa/data/raw/us/_IDX_GSPC_D1.parquet",
              "usa/data/raw/us/SPY_D1.parquet",
              "usa/data/raw/us/SPX_D1.parquet"),
}


class CalendarError(Exception):
    """Raised when calendar cannot be built or a date cannot be resolved."""


def _index_path(root: Path, market: str) -> Path:
    for rel in INDEX_PATHS.get(market.lower(), ()):
        p = root / rel
        if p.exists(): return p
    raise CalendarError(f"no index parquet found for market={market}")


@lru_cache(maxsize=8)
def _sessions_cached(root_str: str, market: str) -> tuple:
    """Return the sorted tuple of ISO-date trading sessions for market."""
    import pandas as pd
    root = Path(root_str)
    p = _index_path(root, market)
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
    return tuple(sorted(df.index))


def sessions(root: Path, market: str) -> List[str]:
    """Full list of ISO trading sessions for a market (cached)."""
    return list(_sessions_cached(str(root), market.lower()))


def is_trading_session(root: Path, market: str, iso_date: str) -> bool:
    """True iff iso_date is an actual trading session per the index parquet."""
    return iso_date in _sessions_cached(str(root), market.lower())


def prior_session(root: Path, market: str, iso_date: str) -> Optional[str]:
    """Return the closest trading session <= iso_date, or None."""
    ss = _sessions_cached(str(root), market.lower())
    earlier = [d for d in ss if d <= iso_date]
    return earlier[-1] if earlier else None


def next_session(root: Path, market: str, iso_date: str) -> Optional[str]:
    """Return the closest trading session > iso_date, or None."""
    ss = _sessions_cached(str(root), market.lower())
    later = [d for d in ss if d > iso_date]
    return later[0] if later else None


def nth_session_after(root: Path, market: str,
                     entry_iso: str, n: int) -> Optional[str]:
    """Return the Nth valid trading session AFTER entry_iso (1-indexed).

    Example: nth_session_after(root, 'india', '2026-08-14', 5) returns the
    5th trading day after 2026-08-14 · which may or may not be
    2026-08-14 + 5 calendar days depending on weekends/holidays.
    """
    if n < 1:
        raise CalendarError(f"n must be >= 1, got {n}")
    ss = _sessions_cached(str(root), market.lower())
    later = [d for d in ss if d > entry_iso]
    if len(later) < n: return None
    return later[n - 1]


def sessions_between(root: Path, market: str,
                    from_iso: str, to_iso: str) -> int:
    """Count of trading sessions strictly after from_iso and <= to_iso."""
    ss = _sessions_cached(str(root), market.lower())
    return sum(1 for d in ss if from_iso < d <= to_iso)


def validate_exit_chain(root: Path, market: str,
                        prediction_date: str,
                        entry_date: str,
                        exit_date: str,
                        as_of: str) -> tuple:
    """Enforce the CEO's exit invariant chain. Returns (ok, reason).

       prediction_date < entry_date <= exit_date
       exit_date ∈ canonical trading calendar
       exit_date <= evaluation/as-of date
    """
    try:
        pd_ = date.fromisoformat(prediction_date[:10])
        ed = date.fromisoformat(entry_date[:10])
        xd = date.fromisoformat(exit_date[:10])
        ao = date.fromisoformat(as_of[:10])
    except Exception as e:
        return (False, f"unparseable date: {e}")
    if not (pd_ < ed):
        return (False, f"prediction_date {prediction_date} !< entry_date {entry_date}")
    if not (ed <= xd):
        return (False, f"entry_date {entry_date} !<= exit_date {exit_date}")
    if not (xd <= ao):
        return (False, f"exit_date {exit_date} > as_of {as_of}")
    if not is_trading_session(root, market, exit_date):
        return (False, f"exit_date {exit_date} not in canonical trading calendar")
    return (True, "OK")


def clear_cache():
    """Reset the sessions cache · call after parquet refreshes in tests."""
    _sessions_cached.cache_clear()
