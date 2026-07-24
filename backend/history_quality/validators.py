"""Sprint B0 · Per-family validation functions (pure)."""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import pandas as pd

from .types import FamilyCheckResult, FamilyStatus
from .metrics import compute_family_score


def _weekdays_between(d0: date, d1: date) -> Set[date]:
    """Enumerate business days (Mon-Fri) inclusive. Best-effort trading-day proxy."""
    out: Set[date] = set()
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            out.add(d)
        d += timedelta(days=1)
    return out


def _read_parquet_safe(p: Path) -> Optional[pd.DataFrame]:
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _parse_asof_series(df: pd.DataFrame) -> Optional[pd.Series]:
    if "asof" not in df.columns:
        return None
    s = pd.to_datetime(df["asof"], errors="coerce").dt.date
    return s.dropna()


# ── History-file validators (per family) ─────────────────────────

def check_history_parquet(*, family: str, path: Path, market: str,
                             required_columns: Iterable[str] = ("market", "asof"),
                             expected_min_rows: int = 1,
                             extra_dedupe_keys: Iterable[str] = (),
                             ) -> FamilyCheckResult:
    """
    Generic append-only history-parquet validator. Used for:
    recommendation_history / risk_history / portfolio_history / execution_history
    / learning_history / macro_history / factor_library_history.

    Checks: existence · schema · row count · duplicate rows on the natural key ·
    missing weekdays in the observed date range (soft signal).

    `extra_dedupe_keys`: extends the natural key beyond (market, asof) for
    multi-row-per-day families like factor_library (keyed on market+asof+factor).
    Passing () treats each date as a snapshot; passing ('factor',) allows one
    row per (market, asof, factor).
    """
    exists = path.exists()
    if not exists:
        score = compute_family_score(exists=False, n_rows=0, n_duplicate_dates=0,
                                        n_missing_trading_days=0, schema_ok=False,
                                        expected_min_rows=expected_min_rows)
        return FamilyCheckResult(
            family=family, file_path=str(path), exists=False,
            status=FamilyStatus.NOT_APPLICABLE.value, quality_score=score,
            notes=["file does not exist (family may be populated over time)"],
        )

    df = _read_parquet_safe(path)
    if df is None:
        return FamilyCheckResult(
            family=family, file_path=str(path), exists=True,
            status=FamilyStatus.FAIL.value, schema_ok=False,
            schema_issues=["parquet read failed"],
            quality_score=compute_family_score(exists=True, n_rows=0,
                                                  n_duplicate_dates=0, n_missing_trading_days=0,
                                                  schema_ok=False, expected_min_rows=expected_min_rows),
        )

    # Filter to market
    if "market" in df.columns:
        df = df[df["market"] == market].copy()
    n_rows = len(df)

    # Schema
    schema_issues: List[str] = []
    schema_ok = True
    for col in required_columns:
        if col not in df.columns:
            schema_ok = False
            schema_issues.append(f"missing column: {col}")

    # Dates
    asof_series = _parse_asof_series(df)
    if asof_series is None or len(asof_series) == 0:
        n_unique = 0
        n_dup = 0
        n_missing = 0
        date_range = None
    else:
        n_unique = int(asof_series.nunique())
        # Dedupe check uses the natural key (asof + extras like `factor` for
        # multi-row-per-day families). Without extras, N rows on the same date
        # are duplicates. With extras, only true collisions on the full natural
        # key count as duplicates.
        dedupe_cols = ["asof"] + [c for c in extra_dedupe_keys if c in df.columns]
        if len(dedupe_cols) > 1:
            key = df[dedupe_cols].astype(str).agg("|".join, axis=1)
            n_dup = int((key.value_counts() > 1).sum())
        else:
            n_dup = int((asof_series.value_counts() > 1).sum())
        dmin, dmax = asof_series.min(), asof_series.max()
        date_range = f"{dmin.isoformat()}..{dmax.isoformat()}"
        expected = _weekdays_between(dmin, dmax)
        present = set(asof_series.tolist())
        n_missing = len(expected - present)

    quality_score = compute_family_score(
        exists=True, n_rows=n_rows,
        n_duplicate_dates=n_dup,
        n_missing_trading_days=n_missing,
        schema_ok=schema_ok,
        expected_min_rows=expected_min_rows,
    )

    if not schema_ok:
        status = FamilyStatus.FAIL.value
    elif n_dup > 0 or n_missing > 5:
        status = FamilyStatus.WARN.value
    elif n_rows == 0:
        status = FamilyStatus.WARN.value
    else:
        status = FamilyStatus.PASS.value

    return FamilyCheckResult(
        family=family, file_path=str(path), exists=True,
        status=status, n_rows=n_rows, n_unique_dates=n_unique,
        n_duplicate_dates=n_dup, n_missing_trading_days=n_missing,
        date_range=date_range, schema_ok=schema_ok, schema_issues=schema_issues,
        quality_score=quality_score,
    )


def check_learning_corpus(*, path: Path, market: str) -> FamilyCheckResult:
    """Learning corpus keyed on (market, ticker, rec_asof) — different from asof-history."""
    if not path.exists():
        return FamilyCheckResult(
            family="learning_corpus", file_path=str(path), exists=False,
            status=FamilyStatus.NOT_APPLICABLE.value,
            quality_score=0,
            notes=["learning corpus builds up as recs close horizons"],
        )
    df = _read_parquet_safe(path)
    if df is None:
        return FamilyCheckResult(
            family="learning_corpus", file_path=str(path), exists=True,
            status=FamilyStatus.FAIL.value, schema_ok=False,
            schema_issues=["parquet read failed"], quality_score=40,
        )
    if "market" in df.columns:
        df = df[df["market"] == market].copy()
    n_rows = len(df)
    required = {"ticker", "rec_asof", "return_pct"}
    missing_cols = required - set(df.columns)
    schema_ok = not missing_cols
    schema_issues = ([f"missing columns: {sorted(missing_cols)}"] if missing_cols else [])

    if n_rows == 0:
        status = FamilyStatus.NOT_APPLICABLE.value
    elif not schema_ok:
        status = FamilyStatus.FAIL.value
    else:
        status = FamilyStatus.PASS.value

    quality_score = compute_family_score(
        exists=True, n_rows=n_rows,
        n_duplicate_dates=0, n_missing_trading_days=0,
        schema_ok=schema_ok, expected_min_rows=5,
    )
    return FamilyCheckResult(
        family="learning_corpus", file_path=str(path), exists=True,
        status=status, n_rows=n_rows, schema_ok=schema_ok,
        schema_issues=schema_issues, quality_score=quality_score,
    )


def check_price_universe(*, raw_dir: Path, market: str,
                            required_min_tickers: int = 10) -> FamilyCheckResult:
    """
    Validate the price-history universe. Scans raw ticker parquets under `raw_dir`
    for count, date-range coverage, and flags any ticker whose latest date is
    substantially behind the fleet median (candidate for corporate-action-adjacent
    stall or delisting).
    """
    if not raw_dir.exists():
        return FamilyCheckResult(
            family="price", file_path=str(raw_dir), exists=False,
            status=FamilyStatus.FAIL.value, quality_score=0,
            schema_issues=[f"raw directory does not exist: {raw_dir}"],
        )

    parquets = sorted(raw_dir.glob("*_D1.parquet"))
    n_tickers = len(parquets)
    if n_tickers < required_min_tickers:
        return FamilyCheckResult(
            family="price", file_path=str(raw_dir), exists=True,
            status=FamilyStatus.FAIL.value, n_rows=n_tickers,
            quality_score=20,
            notes=[f"only {n_tickers} ticker parquets (< {required_min_tickers} required)"],
        )

    latest_dates: List[date] = []
    earliest_dates: List[date] = []
    stalled: List[str] = []
    for p in parquets:
        df = _read_parquet_safe(p)
        if df is None or "close" not in df.columns:
            stalled.append(p.stem)
            continue
        idx = df.index
        if hasattr(idx, "date"):
            dates = [d for d in idx.date if hasattr(d, "isoformat")]
        elif "time" in df.columns:
            dates = pd.to_datetime(df["time"], errors="coerce").dropna().dt.date.tolist()
        else:
            continue
        if not dates:
            stalled.append(p.stem)
            continue
        latest_dates.append(max(dates))
        earliest_dates.append(min(dates))

    if not latest_dates:
        return FamilyCheckResult(
            family="price", file_path=str(raw_dir), exists=True,
            status=FamilyStatus.FAIL.value, n_rows=n_tickers, quality_score=30,
            notes=["no readable ticker prices found"],
        )

    # pandas median doesn't work on datetime.date directly — convert via Timestamp
    latest_ts   = pd.to_datetime([d.isoformat() for d in latest_dates])
    earliest_ts = pd.to_datetime([d.isoformat() for d in earliest_dates])
    latest_median   = latest_ts.min() + (latest_ts.max() - latest_ts.min()) / 2
    earliest_median = earliest_ts.min() + (earliest_ts.max() - earliest_ts.min()) / 2
    latest_median   = latest_median.date()
    earliest_median = earliest_median.date()

    # Flag tickers whose last bar is >3 trading days behind the fleet median (likely stalled)
    for p in parquets:
        df = _read_parquet_safe(p)
        if df is None or "close" not in df.columns: continue
        idx = df.index
        if hasattr(idx, "date"):
            dates = [d for d in idx.date if hasattr(d, "isoformat")]
        elif "time" in df.columns:
            dates = pd.to_datetime(df["time"], errors="coerce").dropna().dt.date.tolist()
        else: continue
        if not dates: continue
        if (latest_median - max(dates)).days > 3:
            stalled.append(p.stem)

    n_stalled = len(set(stalled))
    date_range = f"{earliest_median.isoformat()}..{latest_median.isoformat()}"

    notes: List[str] = []
    if n_stalled > 0:
        notes.append(f"{n_stalled} tickers stalled >3 trading days behind fleet median")
        stalled_sample = sorted(set(stalled))[:10]
        notes.append(f"stalled sample: {stalled_sample}")

    n_missing = max(0, len(_weekdays_between(earliest_median, latest_median)) - int(pd.Series(latest_dates).count()) * 5)
    # ^ rough heuristic; won't drive verdict

    quality_score = compute_family_score(
        exists=True, n_rows=n_tickers,
        n_duplicate_dates=0,
        n_missing_trading_days=min(15, n_stalled),
        schema_ok=True, expected_min_rows=required_min_tickers,
    )

    if n_stalled > n_tickers * 0.20:
        status = FamilyStatus.FAIL.value
    elif n_stalled > 0:
        status = FamilyStatus.WARN.value
    else:
        status = FamilyStatus.PASS.value

    return FamilyCheckResult(
        family="price", file_path=str(raw_dir), exists=True,
        status=status, n_rows=n_tickers, n_unique_dates=int(pd.Series(latest_dates).nunique()),
        n_missing_trading_days=n_stalled,
        date_range=date_range, quality_score=quality_score, notes=notes,
    )
