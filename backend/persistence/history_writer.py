"""
Sprint 7.5 · History Writer.

Append-only, dedupe-on-(market, asof) parquet writer.

CALL CONTRACT (corrected 2026-11-03 · the previous text here was false).
`write_snapshot_and_history` has NO production callers. The two daily
recommendation runners -- india/recommendation_intelligence/run.py and
usa/research/recommendation_intelligence/run.py -- write their own JSON
snapshot and then call `append_snapshot_row` directly. Replay/backfill
calls `append_snapshot_row` via backend/replay/controller.py.

Do not read the old claim ("every engine runner calls ...") as a
description of the system. It described an intention. In eight months of
daily runs the India history received 5 rows and USA 4; 68 of India's 73
rows and 135 of USA's 139 were written by a single replay batch on
2026-07-21. A docstring is not a call site.

New callers should prefer `append_and_record`, which verifies the row
landed and emits a machine-readable persistence state, because the plain
append is fail-open by design and a swallowed failure is indistinguishable
from a successful run that had nothing to say.

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


# ─────────────────────────────────────────────────────────────
# Verified append · CEO 2026-11-03
# ─────────────────────────────────────────────────────────────
#
# append_snapshot_row is fail-open: it returns None and logs rather than
# raising, so the daily JSON snapshot survives a history failure. That was
# a deliberate choice and it stays. What it cost us is observability: both
# daily runners wrapped it in try/except and printed a warning, so a run
# that persisted nothing looked exactly like a run that persisted fine.
#
# append_and_record keeps the fail-open behaviour and adds the missing half:
# it reads the history back, confirms the (market, asof) row is actually
# there, and writes a machine-readable state file a CI step can fail on.
# PERSISTED means verified present, not "the call did not raise".

PERSISTENCE_STATE_DIR = ("reports", "context")


def persistence_state_path(root: str | Path, market: str) -> Path:
    return Path(root).joinpath(*PERSISTENCE_STATE_DIR) / (
        "history_persistence_%s.json" % str(market).lower())


def append_and_record(
    payload: Dict[str, Any],
    history_path: str | Path,
    *,
    root: str | Path,
    market: Optional[str] = None,
    asof_key: str = "asof",
    market_key: str = "market",
) -> Dict[str, Any]:
    """Append, then PROVE the row landed. Returns the state dict it wrote.

    state is one of:
      PERSISTED  · the (market, asof) row is present in the parquet
      FAILED     · the append returned None, or the row is absent after it
      SKIPPED    · the payload carried no asof/market to key on

    Never raises. The caller's snapshot must survive a history failure, but
    the failure must not be invisible.
    """
    history_path = Path(history_path)
    mkt = str(market or payload.get(market_key) or "").lower()
    asof = str(payload.get(asof_key) or "")

    def _rows() -> int:
        try:
            return len(pd.read_parquet(history_path))
        except Exception:
            return 0

    before = _rows()
    state = {
        "market": mkt,
        "asof": asof,
        "history_expected": True,
        "reason": None,
        "history_path": str(history_path),
        "rows_before": before,
        "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": HISTORY_SCHEMA_VERSION,
    }

    if not asof or not mkt:
        state.update(state="SKIPPED", rows_after=before, verified=False,
                     detail="payload carried no %s/%s" % (asof_key, market_key))
    else:
        wrote = append_snapshot_row(payload, history_path,
                                    asof_key=asof_key, market_key=market_key)
        after = _rows()
        verified = False
        try:
            df = pd.read_parquet(history_path)
            verified = bool(len(df[(df[market_key].astype(str).str.lower() == mkt)
                                   & (df[asof_key].astype(str).str[:10] == asof[:10])]))
        except Exception:
            verified = False
        state.update(
            rows_after=after,
            verified=verified,
            state="PERSISTED" if (wrote is not None and verified) else "FAILED",
            detail=("row verified present" if verified else
                    "append returned None" if wrote is None else
                    "append reported success but the row is absent"),
        )

    try:
        sp = persistence_state_path(root, mkt or "unknown")
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception as exc:                        # pragma: no cover
        _log_error(history_path, exc, {"state": state})
    return state


# ─────────────────────────────────────────────────────────────
# Not-attempted states · CEO 2026-11-03
# ─────────────────────────────────────────────────────────────
#
# append_and_record can only speak for runs that REACHED the append. Both
# daily recommendation runners are "optional": True in their orchestrators
# and exit FATAL when ensemble.json or the feature snapshot is absent, so
# the common failure never reached it and left no trace at all. "No state
# file" was therefore ambiguous: it meant either "the step is not wired"
# or "the step died early", and a green daily run looked identical.
#
# record_not_attempted removes the ambiguity. A FATAL exit now says so, in
# a file, with its reason. The distinction that matters downstream:
#
#   history_expected=True   a run that SHOULD have appended and did not
#   history_expected=False  a run with legitimately nothing to append
#
# Only the second may pass a strict check, and only with a reason drawn
# from the vocabulary below - a free-text excuse is not an audit trail.

#: Reasons a run may legitimately persist no history. Anything else is a
#: failure, including an empty or unrecognised reason.
ALLOWED_SKIP_REASONS = {
    "MARKET_HOLIDAY": "no trading session for this market on this date",
    "NO_TRADING_SESSION": "the market calendar has no session to score",
    "RECOMMENDATIONS_NOT_REQUIRED": "this run deliberately produces no "
                                    "recommendations (e.g. a research-only pass)",
}

#: Reason recorded when an upstream precondition killed the runner.
REASON_UPSTREAM_FATAL = "UPSTREAM_FATAL"


def record_not_attempted(
    root: str | Path,
    market: str,
    *,
    reason: str,
    detail: str = "",
    expected: bool = True,
    state: Optional[str] = None,
) -> Dict[str, Any]:
    """Record that this run did not reach the history append, and why.

    `expected=True` (the default) means history SHOULD have been written -
    the resulting state is FAILED and a strict check must fail on it.
    `expected=False` with an ALLOWED_SKIP_REASONS reason means there was
    nothing to write, and a strict check may pass.

    Never raises: it is called from failure paths.
    """
    mkt = str(market).lower()
    st = {
        "market": mkt,
        "asof": None,
        "state": state or ("SKIPPED" if not expected else "FAILED"),
        "history_expected": bool(expected),
        "reason": str(reason or ""),
        "detail": str(detail or ""),
        "verified": False,
        "rows_before": None,
        "rows_after": None,
        "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": HISTORY_SCHEMA_VERSION,
    }
    try:
        p = persistence_state_path(root, mkt or "unknown")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, indent=2, default=str), encoding="utf-8")
    except Exception:                                # pragma: no cover
        pass
    return st
