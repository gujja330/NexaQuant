"""Domain 10 · Corporate events extension · buybacks · dilution · rights · M&A · mgmt changes."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D10-CORP-EVENTS-EXT", domain_num=10,
    name="Corporate events extension",
    description="Beyond dividends/splits · buybacks · dilution · rights · M&A · management changes",
    gate_precondition="SEC 8-K (USA) + BSE/NSE corp-announcements ingest",
    additive_extension_id="D10-CORP-EVENTS-EXT",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "SEC 8-K + BSE/NSE announcement scrapers not wired · need dedicated ingest per market",
                       artifacts=[f"reports/research/deep/d10_corp_events_ext_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
