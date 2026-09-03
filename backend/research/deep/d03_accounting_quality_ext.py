"""Domain 3 · Accounting quality extension · cash-vs-profit divergence · receivables · inventory · one-offs · auditor signals."""
from __future__ import annotations
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result
RESEARCH_TICKET = build_ticket(
    ticket_id="D03-ACCOUNTING-QUALITY-EXT", domain_num=3,
    name="Accounting quality extension (beyond Piotroski/Beneish/Sloan)",
    description="Cash-vs-profit divergence · receivables quality · inventory quality · one-off earnings · auditor signals",
    gate_precondition="Full statement history + auditor-change data (SEC/SEBI filings · not in yfinance)",
    additive_extension_id="D03-ACCOUNTING-EXT",
)
def evaluate(root: Path, market: str) -> dict:
    r = blocked_result(RESEARCH_TICKET, market,
                       "Auditor-change + one-off earnings need direct filings parse (SEC 10-K/10-Q · SEBI annual reports) · not in current ingest",
                       artifacts=[f"reports/research/deep/d03_accounting_quality_ext_{market}.json"])
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, r); return r
