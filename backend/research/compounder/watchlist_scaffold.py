"""Compounder Watchlist · V2 Part C scaffold.

Scaffold ONLY · the actual Winner/Failure Genome program is blocked on
LT-COMPOUNDER-01 (20+ year historical PIT fundamentals · genuinely
external-data blocker · deeper than SAMPLE_TIME).

What this module does today:
  · Registers the ISOLATION CONTRACT machinery (watchlist_id namespace)
  · Publishes the DATA_REQUIREMENT registry entry for LT-COMPOUNDER-01
  · Provides evaluate() so scoring engine test sees it correctly BLOCKED-EVIDENCE
  · Reserves a distinct sheet name (07_Compounder_Watchlist) · not emitted
    into any workbook until data unblocks + program clears its own gates

Never writes to Registry · never writes to 01_Portfolio · never writes to
Exit History. All writes land under reports/research/compounder/ only.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="LT-COMPOUNDER-01",
    domain_num=99,   # C-series · not 1-20 fundamentals map
    name="Compounder Watchlist · V2 Part C · Winner/Failure Genome",
    description="Reconstruct historical (business, balance, growth, valuation, governance, industry, macro) state per PIT date over 20+ years · label with 5/10/15Y forward outcomes · compare winner genome vs failure genome",
    gate_precondition="EXTERNAL_DATA · multi-decade PIT historical fundamentals vendor",
    additive_extension_id="LT-COMPOUNDER-01",
)

# Watchlist ID namespace · structurally distinct from any Position ID
def make_watchlist_id(market: str, ticker: str, listed_date: str) -> str:
    """Format · WL-{MKT}-{TICKER}-{LISTED_DATE} · never confused for a Position ID."""
    m = str(market).upper()
    t = str(ticker).upper().replace(".", "-")
    d = str(listed_date).replace("-", "")
    return f"WL-{m}-{t}-{d}"


# Sheet name reserved · never emitted until Compounder program has evidence to show
COMPOUNDER_SHEET_NAME = "07_Compounder_Watchlist"


# Data-requirement registry · public record of what's blocking the program
DATA_BLOCKERS = {
    "LT-COMPOUNDER-01": {
        "blocker_type": "EXTERNAL_DATA",
        "specific_need": "Multi-decade PIT historical fundamentals · 20+ years",
        "candidate_vendors": [
            "Compustat / S&P Capital IQ (subscription · gold standard)",
            "CMIE Prowess (India · subscription)",
            "yfinance historical (free · but shallower depth than needed)",
            "SEC EDGAR historical 10-K parsing (free · significant engineering lift)",
        ],
        "why_deeper_than_sample_time": (
            "SAMPLE_TIME blockers wait for time · this blocker requires a "
            "different data source we do not currently have. Cannot self-resolve "
            "by running the accumulator longer."
        ),
        "owner_action": (
            "CEO decision · budget allocation for multi-decade fundamentals vendor "
            "OR engineering-time allocation for SEC EDGAR historical parser build. "
            "This program does not advance without one of the two."
        ),
    }
}


def evaluate(root: Path, market: str) -> dict:
    """Watchlist evaluate · honestly reports BLOCKED-EVIDENCE until data arrives.

    Emits result to reports/research/compounder/{market}.json so the coverage
    tracker sees it AND so the CEO's scorecard can render the data-blocker
    ticket every day (it does not go away silently)."""
    out_dir = root / "reports" / "research" / "compounder"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 99,
        "market": market,
        "gate_status": "BLOCKED-EVIDENCE",
        "isolation_contract": {
            "no_position_id": True,
            "watchlist_id_namespace": "WL-{MKT}-{TICKER}-{LISTED_DATE}",
            "no_delivery_sheet_integration_into_existing": True,
            "reserved_sheet_name": COMPOUNDER_SHEET_NAME,
            "sheet_not_emitted_until": "program produces genuine evidence past its own gate",
            "no_auto_sizing_or_auto_recommendation": True,
            "retrospective_only_validation": True,
        },
        "data_blocker": DATA_BLOCKERS["LT-COMPOUNDER-01"],
        "next_gate": (
            "This ticket stays BLOCKED-EVIDENCE until CEO authorizes ONE of · "
            "(A) multi-decade fundamentals vendor subscription · "
            "(B) engineering ticket for SEC EDGAR historical 10-K parser."
        ),
        "verdict": "BLOCKED-EVIDENCE · EXTERNAL_DATA · LT-COMPOUNDER-01 open",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / f"{market}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, payload)
    return payload
