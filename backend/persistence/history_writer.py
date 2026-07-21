"""
Sprint 7.5 · History Writer.

Append-only, dedupe-on-(market, asof) parquet writer.
Every engine runner calls `write_snapshot_and_history(payload, json_path, history_path)`
after producing its daily JSON snapshot. The JSON is overwritten each day
(current-day snapshot), but the history parquet is APPENDED with dedupe
so replaying the same date twice yields exactly one row per date.

Design principles (locked):
- Append-only: never truncate history.
- Dedupe on (market, asof) — most-recent write wins for the same date.
- Deterministic: same payload + same asof → same row.
- Walk-forward safe: history parquets carry an `asof` column that
  downstream (Sprint 8) uses as its replay cursor.
- Fail-open: a history write failure never blocks the current-day JSON.
  The runner still produces its snapshot even if history append fails
  (with an error logged to `reports/persistence_errors.jsonl`).
- Free-stack: pandas + pyarrow only. No paid deps.
"""

from __future__ import annotations
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


HISTORY_SCHEMA_VERSION = "1.0.0"


def _flatten_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce an engine payload dict to a single row of scalar / small-JSON columns.
    - Scalars pass through (int/float/str/bool/None).
    - Nested dicts / lists are JSON-encoded into a single column so the row
      remains flat but the raw payload is recoverable.
    - `model_stamp` is dropped from the flat row (it's fingerprinting metadata,
      captured separately in a `model_stamp_json` column).
    """
    row: Dict[str, Any] = {}
    for k, v in payload.items():
        if k == "model_stamp":
            row["model_stamp_json"] = json.dumps(v, default=str) if v else None
            continue
        if v is None or isinstance(v, (int, float, str, bool)):
            row[k] = v
        else:
            row[k] = json.dumps(v, default=str)
    return row


def append_snapshot_row(
    payload: Dict[str, Any],
    history_path: str | Path,
    *,
    asof_key: str = "asof",
    market_key: str = "market",
) -> Optional[Dict[str, Any]]:
    """
    Append one row (derived from `payload`) to `history_path` (parquet).
    Dedupes on (market, asof) — replaying the same date replaces the row.

    Returns the row dict on success, None on failure (fail-open — never
    raises so the runner's main JSON snapshot is preserved).
    """
    history_path = Path(history_path)
    try:
        row = _flatten_payload(payload)
        row["history_schema_version"] = HISTORY_SCHEMA_VERSION
        row["appended_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        asof = payload.get(asof_key)
        market = payload.get(market_key)
        if not asof or not market:
            _log_error(
                history_path,
                RuntimeError(f"missing {asof_key} or {market_key} in payload"),
                payload,
            )
            return None

        history_path.parent.mkdir(parents=True, exist_ok=True)

        new_df = pd.DataFrame([row])

        if history_path.exists():
            try:
                existing = pd.read_parquet(history_path)
                keep_mask = ~(
                    (existing[market_key] == market) & (existing[asof_key] == asof)
                )
                combined = pd.concat([existing[keep_mask], new_df], ignore_index=True)
            except Exception:
                combined = new_df
        else:
            combined = new_df

        if asof_key in combined.columns:
            combined = combined.sort_values(asof_key, kind="stable").reset_index(drop=True)

        combined.to_parquet(history_path, index=False)
        return row
    except Exception as exc:
        _log_error(history_path, exc, payload)
        return None


def write_snapshot_and_history(
    payload: Dict[str, Any],
    json_path: str | Path,
    history_path: str | Path,
    *,
    asof_key: str = "asof",
    market_key: str = "market",
) -> Dict[str, Any]:
    """
    Convenience wrapper: (1) write current-day JSON snapshot, (2) append to history.
    Returns the payload unchanged so the caller can chain.

    JSON write is authoritative — history append is fail-open (a failed history
    append never blocks the daily snapshot per operator "never affect pipeline" rule).
    """
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    append_snapshot_row(
        payload,
        history_path,
        asof_key=asof_key,
        market_key=market_key,
    )
    return payload


def load_history(history_path: str | Path, *, market: Optional[str] = None) -> pd.DataFrame:
    """
    Load history as a DataFrame (empty DF if file missing).
    If `market` is given, filter to that market only.
    """
    history_path = Path(history_path)
    if not history_path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(history_path)
    if market is not None and "market" in df.columns:
        df = df[df["market"] == market].reset_index(drop=True)
    return df


def _log_error(history_path: Path, exc: Exception, payload: Dict[str, Any]) -> None:
    """
    Fail-open logger: append a JSON line to reports/persistence_errors.jsonl.
    Never raises.
    """
    try:
        root = Path(os.getcwd())
        log = root / "reports" / "persistence_errors.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "history_path": str(history_path),
            "error": str(exc),
            "traceback": traceback.format_exc(limit=3),
            "engine": payload.get("engine"),
            "market": payload.get("market"),
            "asof": payload.get("asof"),
        }
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass
