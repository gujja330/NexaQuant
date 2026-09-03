"""Domain 1 · Business quality · rev/earnings growth · margins · ROIC · FCF conversion · WC · capital allocation."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
from datetime import datetime

RESEARCH_TICKET = build_ticket(
    ticket_id="D01-BUSINESS-QUALITY",
    domain_num=1,
    name="Business quality composite · 9 sub-factors",
    description="Revenue/earnings growth · margin quality · ROIC/ROE · FCF gen · FCF conversion · working capital · capital allocation · reinvestment economics",
    gate_precondition="Historical fundamentals accumulation · ≥8 quarterly snapshots per ticker",
    additive_extension_id="D01-BUSINESS-QUALITY",
)

def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "Historical fundamentals PIT snapshots missing · today's yfinance snapshot only · needs 8+ quarters accumulated for QoQ/YoY factor tests",
                       artifacts=["reports/research/deep/d01_business_quality_" + market + ".json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r)
    return r
