"""Domain 7 · Macro Financial Conditions Index · rates + credit + FX + equity fused."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D07-MACRO-FCI", domain_num=7,
    name="Financial Conditions Index",
    description="Composite of rates + credit spreads + FX + equity risk · BIS-style · yield-curve slope · commodity regime",
    gate_precondition="FRED (USA) + RBI Handbook (India) feeds wired · credit spread series accessible",
    additive_extension_id="D07-MACRO-FCI",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "FCI needs FRED (USA) + RBI Handbook (India) rates+FX+credit-spread feeds · not yet ingested",
                       artifacts=[f"reports/research/deep/d07_macro_fci_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
