"""Domain 4 · Valuation extension · PEG · DCF · reverse DCF · growth-adjusted · sector-relative deep."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D04-VALUATION-EXT", domain_num=4,
    name="Valuation extension · PEG · DCF · reverse DCF · growth-adjusted",
    description="Beyond L2 P/E · EV/EBITDA · FCF yield · TSY · adds DCF-derived intrinsic · reverse DCF · growth-adjusted",
    gate_precondition="Analyst forecast series + WACC estimates + terminal-growth PIT",
    additive_extension_id="D04-VALUATION-EXT",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "DCF requires analyst-forecast time series + WACC per ticker · needs consensus estimate feed · not wired",
                       artifacts=[f"reports/research/deep/d04_valuation_ext_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
