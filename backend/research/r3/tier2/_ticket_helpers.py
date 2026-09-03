"""Shared Research Ticket infrastructure for R3 Tier-2/Tier-3 modules.

Every Tier-2/3 technique publishes:
    RESEARCH_TICKET = build_ticket(...)   # metadata + gate rules
    def evaluate(root, market) -> dict:
        # Returns a dict with keys:
        #   ticket_id, market, gate_status, blocker_reason, artifacts, generated_utc

`gate_status` is one of: BLOCKED-EVIDENCE / INSUFFICIENT_SAMPLE /
NOT_TESTABLE / OK-CANDIDATE / FAIL / PASS.

`BLOCKED-EVIDENCE` is the default for Tier-2/3 · lifts only when R3 shadow
ledger crosses Day-30 kill gate + specific ticket precondition met.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def build_ticket(*, ticket_id: str, tier: int, name: str, description: str,
                 gate_precondition: str, pdf_reference: str,
                 additive_extension_id: str | None = None) -> dict:
    return {
        "ticket_id": ticket_id,
        "tier": tier,
        "name": name,
        "description": description,
        "gate_precondition": gate_precondition,
        "pdf_reference": pdf_reference,
        "additive_extension_id": additive_extension_id,
        "governance": "V2 §21 · additive · never automatic promotion · REJECT is valid research result",
    }


def r3_shadow_ready(root: Path, min_picks: int = 20) -> tuple[bool, str]:
    """Returns (True, "") when R3 shadow ledger has enough picks to open a
    Tier-2 research ticket · else (False, reason)."""
    p = root / "reports" / "research" / "r3" / "shadow_ledger.jsonl"
    if not p.exists():
        return False, "R3 shadow ledger missing"
    try:
        n = 0
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            for l in fh:
                if l.strip(): n += 1
        if n < min_picks:
            return False, f"R3 shadow ledger has {n} < {min_picks} picks · Day-30 gate not fired"
    except Exception as e:
        return False, f"ledger read failed: {e}"
    return True, ""


def blocked_result(ticket: dict, market: str, blocker: str,
                    extra_artifacts: list[str] | None = None) -> dict:
    return {
        "ticket_id": ticket["ticket_id"],
        "tier": ticket["tier"],
        "name": ticket["name"],
        "market": market,
        "gate_status": "BLOCKED-EVIDENCE",
        "blocker_reason": blocker,
        "pdf_reference": ticket["pdf_reference"],
        "artifacts_when_unblocked": extra_artifacts or [],
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "governance_note": ticket["governance"],
    }
