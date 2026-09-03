"""R3 Tier-2 · Promoter + Governance signals · India-specific · PDF R3 Tier-2.

Signals:
  promoter_pledge_pct         · pledged_shares / promoter_total (already in L5)
  promoter_pledge_change_pct  · Δ pledge · quarter-over-quarter (NEW)
  related_party_txn_count     · related-party transactions per year (NEW)
  psu_flag                    · public-sector-undertaking bool (NEW)
  audit_qualification_flag    · qualified audit opinion (NEW)

USA returns None for all (India-only governance signals).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T2-PROMOTER-GOVERNANCE",
    tier=2,
    name="Promoter + Governance signals (India)",
    description="Pledge · related-party txns · PSU · audit qualifications",
    gate_precondition="R3 shadow ≥20 picks + NSE SAST + BSE disclosures ingest wired",
    pdf_reference="V2 §21 · V2 §5 L5 items 19-20 · India-specific governance",
    additive_extension_id="RELATED_PARTY_TXN_SIGNAL",
)


def promoter_pledge_change_pct(now: Optional[float], prev: Optional[float]) -> Optional[float]:
    if now is None or prev is None: return None
    try:
        n = float(now); p = float(prev)
        return round(n - p, 6)
    except (TypeError, ValueError): return None


def related_party_txn_count(fin: dict) -> Optional[int]:
    v = fin.get("related_party_transactions_annual_count")
    if v is None: return None
    try: return int(v)
    except (TypeError, ValueError): return None


def psu_flag(fin: dict) -> Optional[bool]:
    """PSU = Public Sector Undertaking · government-owned Indian entity."""
    v = fin.get("is_psu")
    if v is None: return None
    return bool(v)


def audit_qualification_flag(fin: dict) -> Optional[bool]:
    v = fin.get("audit_report_qualified")
    if v is None: return None
    return bool(v)


def evaluate(root: Path, market: str) -> dict:
    if market != "india":
        return {
            "ticket_id": RESEARCH_TICKET["ticket_id"],
            "market": market,
            "gate_status": "NOT_APPLICABLE",
            "note": "India-only governance signals",
            "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    ok, reason = r3_shadow_ready(root, min_picks=20)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market, reason,
                              extra_artifacts=[
                                  "reports/research/r3/tier2/promoter_governance_india.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Wire NSE SAST + BSE disclosure ingest · populate 4 signals · WF eval as R3 features",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
