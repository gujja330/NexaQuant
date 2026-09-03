"""Shared ticket + gate helpers for the 20 Deep Research domains."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def build_ticket(*, ticket_id: str, domain_num: int, name: str, description: str,
                 gate_precondition: str, additive_extension_id: str | None = None) -> dict:
    return {
        "ticket_id": ticket_id,
        "domain": domain_num,
        "name": name,
        "description": description,
        "gate_precondition": gate_precondition,
        "additive_extension_id": additive_extension_id,
        "governance": "V2 §21 · additive · REJECT is valid research result · no auto-promotion",
    }


def blocked_result(ticket: dict, market: str, blocker: str,
                   artifacts: list[str] | None = None) -> dict:
    return {
        "ticket_id": ticket["ticket_id"],
        "domain": ticket["domain"],
        "market": market,
        "gate_status": "BLOCKED-EVIDENCE",
        "blocker_reason": blocker,
        "artifacts_when_unblocked": artifacts or [],
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def insufficient_sample(ticket: dict, market: str, n: int, need: int) -> dict:
    return {
        "ticket_id": ticket["ticket_id"],
        "domain": ticket["domain"],
        "market": market,
        "gate_status": "INSUFFICIENT_SAMPLE",
        "n": n,
        "required": need,
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_result(root: Path, ticket_id: str, market: str, payload: dict) -> Path:
    out = root / "reports" / "research" / "deep" / f"{ticket_id.lower()}_{market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out
