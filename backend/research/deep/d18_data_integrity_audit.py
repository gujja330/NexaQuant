"""Domain 18 · Data integrity audit · survivorship · look-ahead · revision · missing-data · delisting bias."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from backend.research.deep._helpers import build_ticket, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="D18-DATA-INTEGRITY-AUDIT", domain_num=18,
    name="Data integrity audit · 5 biases",
    description="Survivorship · look-ahead · revision · missing-data · delisting bias · reports gaps per category",
    gate_precondition="Runs any time · reports state · doesn't block",
    additive_extension_id="D18-DATA-INTEGRITY",
)

def evaluate(root: Path, market: str) -> dict:
    from backend.research._paths import price_parquet_dir
    d = price_parquet_dir(root, market)
    files = list(d.glob("*_D1.parquet")) if d.exists() else []
    pit_uni_path = root / "reports" / "research" / "pit_universe" / f"{market}.parquet"
    pit_present = pit_uni_path.exists()

    audit = {
        "survivorship_bias": {
            "risk": "MEDIUM",
            "detail": ("Only today's universe is in parquet · delisted historical tickers "
                       "absent · backtests on this parquet set have upward bias"),
            "mitigation": "Reconstruct historical constituent list (NIFTY 200 · S&P 500 + MidCap 400) · declared as UNIVERSE_EXT_NIFTY200 + MIDCAP400_EXT",
        },
        "look_ahead_bias": {
            "risk": "LOW",
            "detail": "PIT ATR · PIT prices · PIT regime enricher · signal_ledger walks forward correctly",
            "controls": ["PIT rule verified in tests/enrichers/", "walk-forward embargo 5d"],
        },
        "revision_bias": {
            "risk": "MEDIUM",
            "detail": "yfinance fundamentals are current-vintage · original-as-reported not preserved",
            "mitigation": "Would need SEC/SEBI original filings · not currently done",
        },
        "missing_data_bias": {
            "risk": "LOW-MEDIUM",
            "detail": "NULL preserved · never zero-filled per V2 §36 · verified in provider tests",
            "known_gaps": ["FII/DII (India)", "Options PCR", "Transcripts", "13F", "Related-party txns"],
        },
        "delisting_bias": {
            "risk": "MEDIUM",
            "detail": "Delisted tickers vanish from parquet dir · no explicit delisting log",
            "mitigation": "Would need explicit delisting event log · not currently maintained",
        },
    }

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 18, "market": market,
        "gate_status": "EXECUTED",
        "n_parquet_files": len(files),
        "pit_universe_present": pit_present,
        "audit": audit,
        "verdict": "RESEARCH FURTHER · survivorship + revision + delisting biases need mitigation before declaring backtests trustworthy",
        "governance_note": "Data-integrity audit runs any time · findings are informational · do not block experiments but qualify results",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
