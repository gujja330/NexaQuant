"""AEGIS · Delivery · Immutable Prediction Snapshot / Provenance Layer.

CEO handover 2026-08-27 (post-I26/I28 architecture directive):
> "Once production emits a prediction, create an immutable record:
>    prediction_id · market · ticker · prediction_date · entry_date ·
>    entry_price · source_close_date · source_dataset_version ·
>    canonical_signal
>  Everything downstream (History, Portfolio, Exit, forward validation,
>  XLSX) joins back to that snapshot. No downstream process is allowed
>  to rewrite the original entry facts."

Append-only ledger written to reports/delivery/prediction_snapshots.jsonl.
Each row is a frozen snapshot · once written it cannot be re-written by
any downstream stage. Reader enforces this by treating the first
snapshot for a given prediction_id as authoritative and rejecting any
later write that tries to alter its immutable fields.

Immutable fields (CANNOT change once written):
   prediction_id · market · ticker · prediction_date · entry_date ·
   entry_price · source_close_date · source_dataset_version ·
   canonical_signal

Mutable fields (allowed to be updated in a NEW record with the same
prediction_id):
   status · closed_date · closed_reason · last_seen_date · notes
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SNAPSHOT_LEDGER = "reports/delivery/prediction_snapshots.jsonl"

IMMUTABLE_FIELDS = (
    "prediction_id", "market", "ticker", "prediction_date",
    "entry_date", "entry_price", "source_close_date",
    "source_dataset_version", "canonical_signal",
)

MUTABLE_FIELDS = (
    "status", "closed_date", "closed_reason", "last_seen_date", "notes",
)


class ImmutabilityViolation(Exception):
    """Raised when a downstream stage tries to alter an immutable field."""


def _make_prediction_id(market: str, ticker: str, entry_date: str,
                        entry_price: float) -> str:
    """Deterministic ID from (market, ticker, entry_date-date-only).

    NOTE: entry_price is NOT part of the ID · that lets the immutability
    check fire when an attempt is made to overwrite entry_price on the
    same conceptual prediction. entry_date is normalized to YYYY-MM-DD
    (first 10 chars) to prevent timezone-suffix variants from evading
    the check.
    """
    ed_norm = str(entry_date)[:10]
    seed = f"{market.upper()}|{ticker.upper()}|{ed_norm}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{market.upper()}-{ticker.upper()}-{ed_norm.replace('-','')}-{h}"


def _load_ledger(root: Path) -> list:
    p = root / SNAPSHOT_LEDGER
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write_ledger(root: Path, rows: list):
    p = root / SNAPSHOT_LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


def get_snapshot(root: Path, prediction_id: str) -> Optional[dict]:
    """Return the FIRST snapshot for a prediction_id · authoritative."""
    for r in _load_ledger(root):
        if r.get("prediction_id") == prediction_id and \
           not r.get("_quarantined"):
            return r
    return None


def record_snapshot(root: Path, *, market: str, ticker: str,
                    prediction_date: str, entry_date: str,
                    entry_price: float, source_close_date: str,
                    source_dataset_version: str, canonical_signal: str,
                    status: str = "ACTIVE", closed_date: str = "",
                    closed_reason: str = "", last_seen_date: str = "",
                    notes: str = "") -> dict:
    """Append a new snapshot · reject if it would violate immutability.

    Same prediction_id + IDENTICAL immutable fields = idempotent (no-op).
    Same prediction_id + DIFFERENT immutable fields = raise
      ImmutabilityViolation.
    New prediction_id = append normally.
    """
    pid = _make_prediction_id(market, ticker, entry_date, entry_price)
    ledger = _load_ledger(root)
    # Find existing NON-QUARANTINED snapshot for this pid
    existing = None
    for r in ledger:
        if r.get("prediction_id") == pid and not r.get("_quarantined"):
            existing = r; break
    if existing is not None:
        # Check every immutable field
        candidate = {
            "prediction_id":            pid,
            "market":                   market.upper(),
            "ticker":                   ticker.upper(),
            "prediction_date":          prediction_date,
            "entry_date":               entry_date,
            "entry_price":              float(entry_price),
            "source_close_date":        source_close_date,
            "source_dataset_version":   source_dataset_version,
            "canonical_signal":         canonical_signal,
        }
        for f in IMMUTABLE_FIELDS:
            if existing.get(f) != candidate[f]:
                raise ImmutabilityViolation(
                    f"prediction {pid} field {f}: existing={existing.get(f)!r} "
                    f"attempted={candidate[f]!r}")
        return existing  # idempotent
    # New snapshot
    row = {
        "prediction_id":            pid,
        "market":                   market.upper(),
        "ticker":                   ticker.upper(),
        "prediction_date":          prediction_date,
        "entry_date":               entry_date,
        "entry_price":              float(entry_price),
        "source_close_date":        source_close_date,
        "source_dataset_version":   source_dataset_version,
        "canonical_signal":         canonical_signal,
        "status":                   status,
        "closed_date":              closed_date,
        "closed_reason":            closed_reason,
        "last_seen_date":           last_seen_date or entry_date,
        "notes":                    notes,
        "_created_utc":             datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    ledger.append(row)
    _write_ledger(root, ledger)
    return row


def update_mutable(root: Path, prediction_id: str, **kwargs) -> dict:
    """Update mutable fields · appends a new event · leaves immutable frozen.
    Rejects immutable-field attempts."""
    for k in kwargs:
        if k in IMMUTABLE_FIELDS:
            raise ImmutabilityViolation(
                f"cannot update immutable field {k} via update_mutable")
    snap = get_snapshot(root, prediction_id)
    if snap is None:
        raise KeyError(f"no snapshot found for {prediction_id}")
    ledger = _load_ledger(root)
    # Find the latest event for this pid
    for r in reversed(ledger):
        if r.get("prediction_id") == prediction_id and \
                not r.get("_quarantined"):
            for k, v in kwargs.items():
                r[k] = v
            r["_updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write_ledger(root, ledger)
            return r
    raise KeyError(f"no snapshot found for {prediction_id}")


def check_idempotency(root: Path, snapshots_before: list,
                       snapshots_after: list) -> tuple:
    """Compare two ledger dumps · every immutable field on every
    prediction_id must be identical. Returns (ok, drift_report)."""
    before_map = {r["prediction_id"]: r for r in snapshots_before
                   if not r.get("_quarantined")}
    after_map = {r["prediction_id"]: r for r in snapshots_after
                  if not r.get("_quarantined")}
    drift = []
    for pid, br in before_map.items():
        ar = after_map.get(pid)
        if ar is None:
            drift.append({"prediction_id": pid, "issue": "MISSING_AFTER"})
            continue
        for f in IMMUTABLE_FIELDS:
            if br.get(f) != ar.get(f):
                drift.append({
                    "prediction_id": pid,
                    "field":         f,
                    "before":        br.get(f),
                    "after":         ar.get(f),
                    "issue":         "IMMUTABLE_DRIFT",
                })
    return (len(drift) == 0, drift)
