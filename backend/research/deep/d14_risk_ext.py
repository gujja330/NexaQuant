"""Domain 14 · Risk extension · factor concentration · liquidity · gap · tail · stress."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D14-RISK-EXT", domain_num=14,
    name="Risk extension · factor concentration · liquidity · gap · tail · stress",
    description="Beyond existing dynamic-stop + concentration · adds factor concentration · liquidity risk · gap risk · tail risk · portfolio drawdown stress test",
    gate_precondition="Factor library (size/value/momentum betas) + intraday liquidity + historical stress scenarios",
    additive_extension_id="D14-RISK-EXT",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "Factor betas + intraday liquidity + historical crisis scenarios need dedicated build · foundational modules exist elsewhere",
                       artifacts=[f"reports/research/deep/d14_risk_ext_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
