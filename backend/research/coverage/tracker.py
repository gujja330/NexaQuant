"""13-stage Coverage Tracker per CEO 2026-09-03.

STAGE_ORDER (increasing readiness):
    Mapped       · research question identified
    Data-required · fields/source defined but not present
    PIT-ready    · historical reconstruction is possible from available sources
    Populated    · actual usable observations exist (single-day or accumulated)
    Implemented  · feature/test code exists
    Tested       · in-sample evidence produced
    OOS          · out-of-sample evidence produced
    Corrected    · multiple-testing correction applied
    Incremental  · demonstrated to beat / help existing R2
    Paper        · running in paper/shadow comparator
    Shadow       · genuine live shadow evidence accumulating
    Candidate    · eligible for CEO promotion review
    Production   · explicitly approved and running in R2

Honestly hardcoded state · updated as substrate/evidence lands.
"""
from __future__ import annotations

STAGES = [
    "Mapped", "Data-required", "PIT-ready", "Populated",
    "Implemented", "Tested", "OOS", "Corrected",
    "Incremental", "Paper", "Shadow", "Candidate", "Production",
]

# Honest current state per (domain, sub_signal) tuple.
# Updated when new evidence lands.
COVERAGE_MAP = {
    # Domain 1 · Business quality
    ("D01", "Revenue growth"):       "Populated",     # yfinance income series present
    ("D01", "Earnings growth"):      "Populated",
    ("D01", "Margin quality"):       "Implemented",   # in FS L1 as gross_margin_now/prev
    ("D01", "ROIC/ROE"):             "Populated",     # ROA proxy from yfinance · ROIC needs invested capital
    ("D01", "FCF generation"):       "Populated",     # L2 FCF yield populated for 148 tickers
    ("D01", "FCF conversion"):       "Data-required", # (CFO/NI) not yet computed
    ("D01", "Working capital"):      "Data-required", # WC delta yoy not yet
    ("D01", "Capital allocation"):   "Mapped",
    ("D01", "Reinvestment economics"):"Mapped",

    # Domain 2 · Balance sheet
    ("D02", "D/E"):                  "Populated",
    ("D02", "Net Debt/EBITDA"):      "Data-required",
    ("D02", "Interest coverage"):    "Populated",     # L1 populated
    ("D02", "Debt maturity"):        "Data-required",
    ("D02", "Current ratio"):        "Populated",
    ("D02", "Cash quality"):         "Mapped",
    ("D02", "Off-BS exposure"):      "Mapped",

    # Domain 3 · Accounting quality
    ("D03", "Piotroski F"):          "Populated",     # L1 · 148 tickers
    ("D03", "Beneish M"):            "Populated",
    ("D03", "Sloan accruals"):       "Populated",
    ("D03", "Cash-vs-profit divergence"):"Data-required",
    ("D03", "Receivables quality"):  "Data-required",
    ("D03", "Inventory quality"):    "Data-required",
    ("D03", "One-off earnings"):     "Mapped",
    ("D03", "Auditor signals"):      "Mapped",

    # Domain 4 · Valuation
    ("D04", "P/E"):                  "Implemented",
    ("D04", "EV/EBITDA"):            "Populated",     # L2
    ("D04", "FCF yield"):            "Populated",     # L2
    ("D04", "P/B"):                  "Implemented",
    ("D04", "PEG"):                  "Data-required",
    ("D04", "DCF"):                  "Data-required",
    ("D04", "Reverse DCF"):          "Mapped",
    ("D04", "Relative valuation"):   "Populated",     # L2 sector-relative rank
    ("D04", "Sector-relative"):      "Populated",
    ("D04", "Growth-adjusted"):      "Mapped",

    # Domain 5 · Growth quality
    ("D05", "Revenue acceleration"): "Data-required",
    ("D05", "EPS acceleration"):     "Data-required",
    ("D05", "Estimate revisions"):   "Populated",     # L3 analyst_rev_momentum
    ("D05", "Guidance revisions"):   "Populated",
    ("D05", "Earnings surprise"):    "Populated",
    ("D05", "Forward growth vs price"):"Mapped",
    ("D05", "Growth durability"):    "Mapped",

    # Domain 6 · Industry / sector
    ("D06", "Sector momentum"):      "Tested",         # d06 EXECUTED cross-sectional
    ("D06", "Industry leadership"):  "Populated",
    ("D06", "Relative strength"):    "Tested",
    ("D06", "Industry cycle"):       "Data-required",
    ("D06", "Pricing power"):        "Mapped",
    ("D06", "Capacity cycle"):       "Mapped",
    ("D06", "Competitive intensity"):"Mapped",
    ("D06", "Input-cost cycle"):     "Mapped",
    ("D06", "Sector valuation dispersion"):"PIT-ready",

    # Domain 7 · Macro
    ("D07", "Rates"):                "Data-required",
    ("D07", "Inflation"):            "Data-required",
    ("D07", "GDP"):                  "Data-required",
    ("D07", "FX"):                   "Data-required",
    ("D07", "Credit conditions"):    "Data-required",
    ("D07", "Liquidity"):            "Data-required",
    ("D07", "Yield curve"):          "Data-required",
    ("D07", "Commodity regime"):     "Mapped",
    ("D07", "Financial conditions"): "Mapped",

    # Domain 8 · Market structure / flows
    ("D08", "FII/DII"):              "Implemented",   # adapter shim REQUIRES_LIVE_SOURCE
    ("D08", "Options PCR"):          "Implemented",
    ("D08", "Short interest"):       "Populated",     # L4 partial
    ("D08", "Volume"):               "Populated",
    ("D08", "Liquidity"):            "Populated",     # ADV from D14
    ("D08", "Institutional ownership"):"Data-required",
    ("D08", "Ownership concentration"):"Data-required",
    ("D08", "Crowding"):             "Mapped",

    # Domain 9 · Technical / price
    ("D09", "Momentum"):             "Tested",
    ("D09", "Trend"):                "Tested",
    ("D09", "RSI"):                  "Populated",
    ("D09", "ATR"):                  "Tested",         # P0 uses ATR
    ("D09", "Volatility"):           "Populated",
    ("D09", "Volume confirmation"):  "Tested",         # d09 breakout uses vol confirm
    ("D09", "Breakout quality"):     "Tested",         # d09 · REJECT verdict
    ("D09", "Relative strength"):    "Populated",
    ("D09", "Drawdown/recovery"):    "Tested",         # d09 dd stats
    ("D09", "Tail behaviour"):       "Tested",         # d09 kurtosis

    # Domain 10 · Corporate events
    ("D10", "Earnings calendar"):    "Populated",     # L5 window populated
    ("D10", "Earnings surprise"):    "Populated",
    ("D10", "Corporate actions"):    "Populated",     # dividends/splits in parquet
    ("D10", "Buybacks"):             "Data-required",
    ("D10", "Dilution"):             "Data-required",
    ("D10", "Rights issues"):        "Data-required",
    ("D10", "M&A"):                  "Mapped",
    ("D10", "Management changes"):   "Mapped",

    # Domain 11 · Governance (India)
    ("D11", "Promoter pledge"):      "Implemented",   # L5 module · needs ingest
    ("D11", "Related parties"):      "Implemented",   # extended L5 · REQUIRES_LIVE_SOURCE
    ("D11", "Insider transactions"): "Populated",     # L3 insider_f4 populated
    ("D11", "Auditor quality"):      "Mapped",
    ("D11", "Board independence"):   "Mapped",
    ("D11", "Governance controversies"):"Mapped",
    ("D11", "Capital allocation"):   "Mapped",

    # Domain 12 · Narrative / information
    ("D12", "News sentiment"):       "Populated",     # existing news pipeline
    ("D12", "Transcript prepared remarks"):"Implemented",  # Tier-2 scaffold + lexicon
    ("D12", "Transcript Q&A"):       "Implemented",   # SEPARATE per V2 §5
    ("D12", "Guidance language"):    "Populated",
    ("D12", "Management consistency"):"Mapped",
    ("D12", "Narrative-vs-numbers divergence"):"Mapped",

    # Domain 13 · Knowledge graph
    ("D13", "Communities"):          "Populated",     # backfill scaffold + hook
    ("D13", "Community stability"):  "Data-required",
    ("D13", "Ownership relationships"):"Mapped",
    ("D13", "Supplier/customer"):    "Mapped",
    ("D13", "Peer relationships"):   "Populated",

    # Domain 14 · Risk
    ("D14", "Single-stock risk"):    "Tested",         # d14 correlation + tail
    ("D14", "Sector concentration"): "Tested",
    ("D14", "Factor concentration"): "Data-required",
    ("D14", "Correlation"):          "Tested",         # d14 real
    ("D14", "Liquidity risk"):       "Populated",
    ("D14", "Gap risk"):             "PIT-ready",
    ("D14", "Event risk"):           "Populated",
    ("D14", "Tail risk"):            "Tested",         # d14 VaR
    ("D14", "Portfolio drawdown"):   "Tested",
    ("D14", "Stress testing"):       "Mapped",

    # Domain 15 · Portfolio construction
    ("D15", "Position sizing"):      "Implemented",
    ("D15", "Kelly / fractional"):   "Tested",         # d15 Kelly EXECUTED
    ("D15", "Correlation-aware sizing"):"Populated",   # data available · sizing rule not
    ("D15", "Sector caps"):          "Implemented",
    ("D15", "Factor neutrality"):    "Implemented",    # R3 T2 factor-neutral scaffolded
    ("D15", "Turnover"):             "Populated",
    ("D15", "Capacity"):             "Mapped",
    ("D15", "Cash allocation"):      "Mapped",

    # Domain 16 · Exit science
    ("D16", "Dynamic ATR"):          "Tested",         # P0 tests
    ("D16", "Target"):               "Tested",
    ("D16", "Stop"):                 "Tested",
    ("D16", "Time exit"):            "Tested",
    ("D16", "Signal deterioration"): "Data-required",  # needs signal ledger history
    ("D16", "Regime exit"):          "Populated",      # regime enricher live
    ("D16", "MAE/MFE"):              "Tested",         # d16 EXECUTED USA
    ("D16", "Winner preservation"):  "Tested",         # POS-PNL
    ("D16", "Loss containment"):     "Tested",         # NEG-PNL

    # Domain 17 · Cross-market / global
    ("D17", "India"):                "Populated",
    ("D17", "USA"):                  "Populated",
    ("D17", "USD/INR"):              "Data-required",
    ("D17", "US rates → India"):    "Mapped",
    ("D17", "Global risk regime"):   "Populated",
    ("D17", "Commodity transmission"):"Mapped",

    # Domain 18 · Data integrity
    ("D18", "PIT universe"):         "Populated",     # 33540 USA · 3250 India (NIFTY 50)
    ("D18", "PIT fundamentals"):     "Data-required", # single-day snapshot only
    ("D18", "PIT sector"):           "Populated",
    ("D18", "PIT KG"):               "Data-required",
    ("D18", "Survivorship bias"):    "Tested",         # d18 audit
    ("D18", "Look-ahead bias"):      "Corrected",      # PIT tests
    ("D18", "Revision bias"):        "Tested",
    ("D18", "Missing-data bias"):    "Corrected",      # NULL preserved
    ("D18", "Delisting bias"):       "Tested",

    # Domain 19 · Statistical robustness
    ("D19", "Walk-forward"):         "Implemented",   # engine ready
    ("D19", "OOS"):                  "Populated",
    ("D19", "DSR"):                  "Populated",     # applied to P0-EXT
    ("D19", "Reality Check"):        "Mapped",
    ("D19", "Multiple testing"):     "Populated",     # trial matrix
    ("D19", "Bootstrap"):            "Tested",         # 10k paired everywhere
    ("D19", "Regime splits"):        "Populated",
    ("D19", "Stability"):            "Mapped",

    # Domain 20 · Failure research
    ("D20", "Why winners missed"):   "Tested",         # POS-PNL
    ("D20", "Why losers occurred"):  "Tested",         # NEG-PNL
    ("D20", "Zero-entry diagnosis"): "Tested",         # E-002 CLOSED
    ("D20", "Model disagreement"):   "Implemented",   # P5.1
    ("D20", "Data failure"):         "Populated",
    ("D20", "Regime failure"):       "Populated",
    ("D20", "Portfolio failure"):    "Data-required",  # needs PIT portfolio state
}


def coverage_summary() -> dict:
    """Aggregate count per stage."""
    from collections import Counter
    counts = Counter(COVERAGE_MAP.values())
    total = sum(counts.values())
    return {
        "total_signals_tracked": total,
        "counts_per_stage": {s: counts.get(s, 0) for s in STAGES},
        "pct_per_stage": {s: round(counts.get(s, 0) / total * 100, 1) for s in STAGES},
        "in_production_pct": round(counts.get("Production", 0) / total * 100, 1),
    }


def coverage_full() -> list[dict]:
    """One row per (domain, sub_signal) with its stage."""
    return [
        {"domain": d, "signal": s, "stage": stage,
         "stage_ordinal": STAGES.index(stage)}
        for (d, s), stage in COVERAGE_MAP.items()
    ]


def coverage_by_domain() -> dict:
    """Grouped by domain · list of signals with stage."""
    from collections import defaultdict
    out = defaultdict(list)
    for (d, s), stage in COVERAGE_MAP.items():
        out[d].append({"signal": s, "stage": stage})
    return dict(out)


def domain_readiness_score(domain: str) -> dict:
    """Domain-level readiness · 0-100 based on average stage ordinal."""
    sigs = [stage for (d, _), stage in COVERAGE_MAP.items() if d == domain]
    if not sigs: return {"domain": domain, "n_signals": 0, "score": 0}
    avg_ord = sum(STAGES.index(s) for s in sigs) / len(sigs)
    max_ord = len(STAGES) - 1
    return {
        "domain": domain, "n_signals": len(sigs),
        "avg_stage_ordinal": round(avg_ord, 2),
        "readiness_pct": round(avg_ord / max_ord * 100, 1),
        "highest_stage_reached": max(STAGES.index(s) for s in sigs),
        "lowest_stage_reached": min(STAGES.index(s) for s in sigs),
    }
