"""Domain 2 · Balance-sheet risk · D/E · Net Debt/EBITDA · Interest Cov · maturity · liquidity · cash quality · off-BS."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D02-BALANCE-SHEET-RISK", domain_num=2,
    name="Balance-sheet risk composite",
    description="D/E · Net Debt/EBITDA · Interest Cov · debt maturity/refinancing · current ratio · cash quality · off-BS exposure",
    gate_precondition="Full statement history + debt-maturity schedule (yfinance free tier lacks maturity/off-BS)",
    additive_extension_id="D02-BALANCE-SHEET",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "yfinance free tier lacks debt-maturity schedule + off-balance-sheet exposure · need paid source (S&P Cap IQ / MoneyControl full statements) OR SEC 10-K parsing",
                       artifacts=[f"reports/research/deep/d02_balance_sheet_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
