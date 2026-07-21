"""
Sprint 7.6 · History integrity validation.

Given an append-only history parquet, checks:
  - missing trading days (against a canonical trading-day set)
  - duplicate dates (should be zero — dedupe key is (market, asof))
  - schema OK (required columns present)

Emits a HistoryValidation record. Used by history_validation.json report
and by the walk-forward readiness gate.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Set

import pandas as pd

from .types import HistoryValidation


def enumerate_trading_days(date_from: date, date_to: date, *, market: str = "usa") -> List[date]:
    """
    Best-effort trading-day enumerator: weekdays between date_from and date_to inclusive.
    We do NOT hard-code exchange holiday calendars — instead the caller compares
    against the actual `asof` dates present in raw price data (see below).
    """
    days: List[date] = []
    d = date_from
    while d <= date_to:
        if d.weekday() < 5:                # Mon..Fri
            days.append(d)
        d += timedelta(days=1)
    return days


def trading_days_from_raw(reference_parquet: Path,
                            date_from: date, date_to: date) -> Set[date]:
    """
    Canonical trading-day set = distinct trading dates that appear in
    the reference raw price parquet within [date_from, date_to].

    This is more accurate than a plain weekday enumeration because it
    respects real exchange holidays and half-days.
    """
    if not reference_parquet.exists():
        return set(enumerate_trading_days(date_from, date_to))
    try:
        df = pd.read_parquet(reference_parquet)
        idx = df.index
        if hasattr(idx, "date"):
            dates = {d for d in idx.date if date_from <= d <= date_to}
        elif "time" in df.columns:
            times = pd.to_datetime(df["time"])
            dates = {d.date() for d in times if date_from <= d.date() <= date_to}
        elif "asof" in df.columns:
            dates = {pd.to_datetime(x).date() for x in df["asof"]
                       if date_from <= pd.to_datetime(x).date() <= date_to}
        else:
            return set(enumerate_trading_days(date_from, date_to))
        return dates
    except Exception:
        return set(enumerate_trading_days(date_from, date_to))


def validate_history(history_path: Path, *, market: str,
                       expected_dates: Optional[Set[date]] = None,
                       required_columns: Iterable[str] = ("market", "asof"),
                       ) -> HistoryValidation:
    """
    Validate an append-only history parquet.
      - `expected_dates`: canonical trading-day set to check for gaps (None → no gap check)
      - `required_columns`: schema check
    """
    file_str = str(history_path)
    if not history_path.exists():
        return HistoryValidation(
            file=file_str, market=market,
            n_rows=0, n_unique_dates=0,
            n_missing_trading_days=(len(expected_dates) if expected_dates else 0),
            n_duplicate_dates=0, schema_ok=False,
            schema_notes=["history file does not exist"],
            date_range=None, verdict="FAIL",
        )

    try:
        df = pd.read_parquet(history_path)
    except Exception as e:
        return HistoryValidation(
            file=file_str, market=market,
            n_rows=0, n_unique_dates=0,
            n_missing_trading_days=0, n_duplicate_dates=0,
            schema_ok=False, schema_notes=[f"parquet read failed: {e}"],
            date_range=None, verdict="FAIL",
        )

    if market and "market" in df.columns:
        df = df[df["market"] == market]

    n_rows = len(df)
    if n_rows == 0:
        return HistoryValidation(
            file=file_str, market=market,
            n_rows=0, n_unique_dates=0,
            n_missing_trading_days=(len(expected_dates) if expected_dates else 0),
            n_duplicate_dates=0, schema_ok=True,
            schema_notes=[], date_range=None, verdict="WARN",
        )

    schema_notes: List[str] = []
    schema_ok = True
    for col in required_columns:
        if col not in df.columns:
            schema_ok = False
            schema_notes.append(f"missing column: {col}")

    if "asof" in df.columns:
        asof_series = pd.to_datetime(df["asof"], errors="coerce").dt.date
        asof_present = {d for d in asof_series if pd.notna(d)}
        counts = asof_series.value_counts()
        n_duplicate_dates = int((counts > 1).sum())
        date_range = f"{min(asof_present)}..{max(asof_present)}" if asof_present else None
    else:
        asof_present = set()
        n_duplicate_dates = 0
        date_range = None
        schema_ok = False
        schema_notes.append("no asof column — cannot check dates")

    if expected_dates is not None:
        n_missing = len(expected_dates - asof_present)
    else:
        n_missing = 0

    verdict = "PASS"
    if not schema_ok:
        verdict = "FAIL"
    elif n_duplicate_dates > 0 or (expected_dates and n_missing > len(expected_dates) * 0.5):
        verdict = "WARN"

    return HistoryValidation(
        file=file_str, market=market,
        n_rows=n_rows, n_unique_dates=len(asof_present),
        n_missing_trading_days=n_missing,
        n_duplicate_dates=n_duplicate_dates,
        schema_ok=schema_ok, schema_notes=schema_notes,
        date_range=date_range, verdict=verdict,
    )
