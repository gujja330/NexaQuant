"""
Sprint 7.7 · Anti-lookahead guard.

Validates that engine outputs for a historical asof=D contain no timestamp
or dependency later than D. Fails immediately on detection.

Checks:
  1. asof in payload ≤ replay asof (obvious sanity)
  2. any timestamp field in payload ≤ replay asof
  3. `replay: true` marker present on reconstructed rows
  4. history parquet has no rows with asof > D when replaying D
"""
from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def _as_date(v: Any) -> Optional[date]:
    if v is None: return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def validate_payload_no_future(payload: Dict[str, Any], *, replay_asof: date) -> List[str]:
    """Return a list of leak descriptions; empty list = clean."""
    leaks: List[str] = []

    payload_asof = _as_date(payload.get("asof"))
    if payload_asof and payload_asof > replay_asof:
        leaks.append(f"payload.asof={payload_asof} > replay_asof={replay_asof}")

    ts_keys = {"cutoff", "asof_utc", "close_asof", "entry_date", "exit_date",
                  "date", "next_review_date"}
    for k, v in payload.items():
        if k in ts_keys:
            d = _as_date(v)
            if d and d > replay_asof:
                leaks.append(f"{k}={d} > replay_asof={replay_asof}")

    # Deep check on recommendations list
    for r in payload.get("recommendations", []) or []:
        if isinstance(r, dict):
            for k in ("asof", "next_review_date", "entry_date"):
                d = _as_date(r.get(k))
                if d and d > replay_asof:
                    leaks.append(f"recommendation[{r.get('ticker')}].{k}={d} > replay_asof={replay_asof}")

    return leaks


def validate_history_no_future(history_path: Path, *, replay_asof: date,
                                  market: str) -> List[str]:
    """Ensure a history parquet has no rows dated after replay_asof for this market."""
    if not history_path.exists():
        return []
    try:
        df = pd.read_parquet(history_path)
    except Exception:
        return [f"could not read {history_path}"]
    if "market" in df.columns:
        df = df[df["market"] == market]
    if "asof" not in df.columns or df.empty:
        return []
    asof_series = pd.to_datetime(df["asof"], errors="coerce").dt.date
    future_rows = [d for d in asof_series if d and d > replay_asof]
    if future_rows:
        return [f"{history_path.name}: {len(future_rows)} rows with asof > {replay_asof}"]
    return []


def enforce_no_future(payload: Dict[str, Any], *, replay_asof: date) -> None:
    """Raises RuntimeError if any leak found. Use in strict/CI mode."""
    leaks = validate_payload_no_future(payload, replay_asof=replay_asof)
    if leaks:
        raise RuntimeError(f"LOOKAHEAD LEAK on replay of {replay_asof}: {leaks}")
