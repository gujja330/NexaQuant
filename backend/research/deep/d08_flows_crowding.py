"""Domain 8 · Flows extension · institutional ownership · concentration · crowding."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D08-FLOWS-CROWDING", domain_num=8,
    name="Flows extension · ownership · concentration · crowding",
    description="Beyond FII/DII + PCR + short-interest · adds institutional ownership · ownership concentration · crowding proxy",
    gate_precondition="13F ingest (USA) + SAST 5%+ disclosures (India) + short-interest history",
    additive_extension_id="D08-FLOWS-CROWDING",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "13F ingest (SEC EDGAR) + SAST parse + short-interest history not wired · REQUIRES_LIVE_SOURCE",
                       artifacts=[f"reports/research/deep/d08_flows_crowding_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
