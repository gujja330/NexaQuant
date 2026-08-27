"""AEGIS · Delivery · Quarantine + Reconstruction Procedure.

CEO handover 2026-08-27 (post-I26/I28 architecture directive):
> "detect corrupted record → quarantine record → identify original
>  prediction snapshot → reconstruct from authoritative source →
>  validate provenance → restore corrected immutable record → record
>  repair/audit event → rerun full pipeline. If the original
>  authoritative value cannot be reconstructed confidently, the row
>  should remain quarantined / insufficient evidence, not be silently
>  repaired."

Append-only events to reports/delivery/quarantine_audit.jsonl.
Never mutates the source record · quarantine is a MARK, not a delete.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

QUARANTINE_LEDGER = "reports/delivery/quarantine_audit.jsonl"


def _append_audit(root: Path, event: dict):
    p = root / QUARANTINE_LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    event["_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")


def quarantine(root: Path, *, source_file: str, record_key: str,
               reason: str, evidence: dict) -> dict:
    """Mark a record as QUARANTINED · append audit event · never mutates
    the source record. Downstream consumers must filter quarantined
    records out."""
    event = {
        "action":       "QUARANTINE",
        "source_file":  source_file,
        "record_key":   record_key,
        "reason":       reason,
        "evidence":     evidence,
    }
    _append_audit(root, event)
    return event


def reconstruct(root: Path, *, source_file: str, record_key: str,
                proposed_immutable_fields: dict,
                authoritative_source: str, provenance: dict) -> dict:
    """Propose a reconstructed authoritative version of a quarantined
    record. Requires an explicit `authoritative_source` (e.g. yfinance
    Aug 20 close) and full `provenance` dict.
    Does NOT auto-write the correction · the caller (CEO-approved
    operator) writes the record via prediction_snapshot.record_snapshot.
    """
    event = {
        "action":                       "RECONSTRUCT_PROPOSED",
        "source_file":                  source_file,
        "record_key":                   record_key,
        "proposed_immutable_fields":    proposed_immutable_fields,
        "authoritative_source":         authoritative_source,
        "provenance":                   provenance,
    }
    _append_audit(root, event)
    return event


def restore(root: Path, *, record_key: str,
            applied_immutable_fields: dict,
            operator: str, approval: str) -> dict:
    """Log the physical write of a reconstructed record. Called AFTER
    the corrected snapshot has been written · this is the audit
    trail."""
    event = {
        "action":                    "RESTORE",
        "record_key":                record_key,
        "applied_immutable_fields":  applied_immutable_fields,
        "operator":                  operator,
        "approval":                  approval,
    }
    _append_audit(root, event)
    return event


def cannot_reconstruct(root: Path, *, record_key: str,
                        reason: str, evidence: dict) -> dict:
    """Log that a record cannot be confidently reconstructed and remains
    in insufficient_evidence status · NOT silently repaired."""
    event = {
        "action":       "CANNOT_RECONSTRUCT_KEEP_QUARANTINED",
        "record_key":   record_key,
        "reason":       reason,
        "evidence":     evidence,
    }
    _append_audit(root, event)
    return event


def is_quarantined(root: Path, record_key: str) -> bool:
    """True iff the record was quarantined AND has NOT been RESTOREd.

    The rule: quarantine can only be lifted by an explicit RESTORE event.
    CANNOT_RECONSTRUCT_KEEP_QUARANTINED · RECONSTRUCT_PROPOSED · and any
    other non-RESTORE audit action leave the record in the quarantined
    state. Only RESTORE lifts it.
    """
    p = root / QUARANTINE_LEDGER
    if not p.exists(): return False
    quarantined = False
    restored_after = False
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try: r = json.loads(ln)
        except Exception: continue
        if r.get("record_key") != record_key: continue
        action = r.get("action")
        if action == "QUARANTINE":
            quarantined = True
            restored_after = False
        elif action == "RESTORE" and quarantined:
            restored_after = True
    return quarantined and not restored_after


def audit_log_for(root: Path, record_key: str) -> list:
    """Return the full audit trail for a specific record_key."""
    p = root / QUARANTINE_LEDGER
    if not p.exists(): return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try: r = json.loads(ln)
        except Exception: continue
        if r.get("record_key") == record_key:
            out.append(r)
    return out
