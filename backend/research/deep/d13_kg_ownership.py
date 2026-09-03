"""Domain 13 · KG ownership + supplier/customer relationships."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D13-KG-OWNERSHIP", domain_num=13,
    name="KG ownership + supplier/customer graph",
    description="Beyond existing KG communities · adds ownership relationships + supplier/customer edges + peer distance stability",
    gate_precondition="13F ownership + supply-chain relationship data (Bloomberg/S&P Cap IQ · not free)",
    additive_extension_id="D13-KG-OWNERSHIP",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "Ownership graph + supplier/customer edges need paid data (Bloomberg SPLC / S&P Cap IQ) · free proxies insufficient",
                       artifacts=[f"reports/research/deep/d13_kg_ownership_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
