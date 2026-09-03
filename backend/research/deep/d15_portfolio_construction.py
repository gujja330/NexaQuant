"""Domain 15 · Portfolio construction · Kelly · correlation-aware · capacity · cash allocation."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D15-PORTFOLIO-CONSTRUCTION", domain_num=15,
    name="Portfolio construction · Kelly + correlation + capacity",
    description="Fractional Kelly sizing · correlation-aware sizing · capacity model · cash allocation policy · position sizing under regime",
    gate_precondition="Historical portfolio state PIT reconstruction · trade-history-cache extended per-day",
    additive_extension_id="D15-PORTFOLIO-CONSTRUCTION",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "Historical portfolio-state PIT not yet reconstructed · Registry has current state · needs nightly snapshot for backtesting sizing rules",
                       artifacts=[f"reports/research/deep/d15_portfolio_construction_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
