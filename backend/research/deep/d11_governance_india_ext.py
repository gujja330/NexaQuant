"""Domain 11 · Governance India extension · board · auditor quality · controversies · remuneration."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D11-GOV-INDIA-EXT", domain_num=11,
    name="Governance India extension",
    description="Board independence · auditor change signals · governance controversies · remuneration signals · capital allocation quality",
    gate_precondition="SEBI CG disclosures + BSE annual-report NLP + media-watchdog feeds",
    additive_extension_id="D11-GOV-INDIA-EXT",
)
def evaluate(root: Path, market: str) -> dict:
    if market != "india":
        from datetime import datetime
        r = {"ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 11, "market": market,
             "gate_status": "NOT_APPLICABLE", "note": "India-only governance signals",
             "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
        emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
    r = blocked_result(RESEARCH_TICKET, market,
                       "SEBI CG disclosures + BSE annual-report NLP + media watchdog feeds not wired · scrapers + legal-NLP required",
                       artifacts=["reports/research/deep/d11_governance_india_ext_india.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
