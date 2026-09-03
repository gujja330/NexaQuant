"""Domain 5 · Growth quality · durability · forward-growth-vs-price."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D05-GROWTH-QUALITY", domain_num=5,
    name="Growth quality · durability + forward vs price",
    description="Revenue acceleration · EPS acceleration · estimate revisions · guidance · surprise · growth durability · forward growth vs price",
    gate_precondition="Estimate revision history + guidance history",
    additive_extension_id="D05-GROWTH-QUALITY",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "Estimate revision + guidance history needs consensus feed (I/B/E/S · Bloomberg · not in yfinance)",
                       artifacts=[f"reports/research/deep/d05_growth_quality_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
