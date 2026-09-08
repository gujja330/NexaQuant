"""ML DISCOVERY v1 · HYPOTHESIS LEDGER · CEO 2026-09-08.

> "If LightGBM discovers `MA200 distance + volatility + confidence`, that
>  is NOT a trading rule. It becomes a registered hypothesis such as
>  MLDISC-MA200-VOL-CONF-001. Then the existing evidence machinery tests
>  it independently."

ML accelerates discovery; it does not bypass a gate. Every candidate
leaves this layer as an append-only ledger entry with a stable id, the
substrate verdict it was found under, and an explicit next-gate. Nothing
here writes to R2, R3, the registry, or any engine.

A hypothesis discovered under CROSS_SECTIONAL_HYPOTHESIS carries that
status permanently in its record. It cannot be quietly re-described as
time-validated later; a new run under a better substrate creates a NEW
entry, and the old one stays as it was.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.ledger.v1"
NEXT_GATE = "EVIDENCE_ENGINE_STATISTICAL_CONFIRMATION"


def ledger_path(root: Path) -> Path:
    return (root / "reports" / "research" / "ml_discovery"
            / "hypothesis_ledger.jsonl")


def make_id(market: str, kind: str, parts: list) -> str:
    stem = "-".join(str(p).upper().replace("_", "")[:6] for p in parts[:3])
    sig = hashlib.sha1(
        ("|".join([market, kind] + [str(p) for p in parts])).encode()
    ).hexdigest()[:4].upper()
    return f"MLDISC-{market.upper()[:3]}-{stem}-{sig}"


def existing_ids(root: Path) -> set:
    p = ledger_path(root)
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.add(json.loads(line).get("hypothesis_id"))
        except Exception:
            continue
    return out


def register(root: Path, market: str, kind: str, parts: list,
             substrate_verdict: str, evidence: dict,
             horizon: str) -> Optional[dict]:
    """Append-only · an id is written once and never rewritten."""
    hid = make_id(market, kind, parts)
    if hid in existing_ids(root):
        return None
    rec = {
        "schema_version": SCHEMA_VERSION,
        "hypothesis_id": hid,
        "market": market.lower(),
        "kind": kind,
        "components": parts,
        "horizon": horizon,
        "substrate_verdict": substrate_verdict,
        "discovered_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence": evidence,
        "status": "REGISTERED_UNTESTED",
        "next_gate": NEXT_GATE,
        "production_impact": "NONE · discovery layer writes to no engine",
        "caveat": (
            "Discovered under %s. A cross-sectional discovery says nothing "
            "about persistence through time and may never be described as "
            "validated on this basis." % substrate_verdict),
    }
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
    return rec


def invalidate(root: Path, hypothesis_id: str, reason: str) -> dict:
    """Retract by APPENDING, never by deleting.

    A hypothesis registered under a substrate verdict that later proves
    wrong must not silently vanish - the record that it was once believed
    is itself evidence. This appends a retraction referencing the id; the
    original entry stays exactly as written.
    """
    rec = {
        "schema_version": SCHEMA_VERSION,
        "hypothesis_id": hypothesis_id,
        "record_type": "RETRACTION",
        "status": "INVALIDATED",
        "reason": reason,
        "retracted_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
    return rec


def active(root: Path) -> list:
    """Entries not superseded by a retraction."""
    rows = load_all(root)
    dead = {r["hypothesis_id"] for r in rows
            if r.get("record_type") == "RETRACTION"}
    return [r for r in rows
            if r.get("record_type") != "RETRACTION"
            and r.get("hypothesis_id") not in dead]


def load_all(root: Path) -> list:
    p = ledger_path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out
