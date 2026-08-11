"""AEGIS Research Platform.

Permanent institutional framework for evaluating ANY idea before it reaches
production. Every candidate — Runner 1 · Runner 2 · Intraday · new Risk
Model · new Position Sizing · new Alpha Filter · Sector Rotation v2 · Macro
Overlay · future models — flows through the same lifecycle:

    Idea → Research Ticket → Historical Backtest → Paper Portfolio →
    60d Live → 90d Validation → CEO Review → Production

Three evidence layers per candidate:
    1. Historical   · did it work in the past?
    2. Live         · does it still work today?
    3. Explainability · why did it win/lose today?

Governance:
    · Article IX  · Research Lifecycle · no shortcuts, ever
    · Article X   · Evidence-First Promotion · every production change
                     requires a completed 90-day ticket

Unified SSoT emitted at every daily run:
    reports/research/research_platform.json

CEO-locked P0 (2026-08-11): every research query sources from
outcome_dataset.parquet · never from XLSX. This prevents the class of bug
where different analyses of the same data produce contradictory numbers
(the Investability 75%-vs-25% mismatch that triggered this lock).

2026-08-11 restore: commit d0c369e7 accidentally replaced this file with
a stub docstring, dropping every re-export. `backend.recommendation.ssot.run`
imports 12 symbols from this package (line 58-67) which broke on both
markets. The full re-export list below is the SSoT for the research API.
Adding a symbol here IS the promotion action; do not import from submodules
directly in downstream code.
"""
from .platform import build_research_platform
from .metrics import compute_runner_metrics, RunnerMetrics
from .paper_portfolio import (
    ingest_runner1_picks_for_date,
    ingest_runner2_picks_for_date,
    ingest_runner2_picks_usa_for_date,
    mark_to_market,
    compute_head_to_head_summary,
)
from .intraday_paper import (
    ingest_runner1_intraday_picks_for_date,
    ingest_runner2_intraday_picks_for_date,
)
from .intraday_hourly import fetch_hourly_bars, ingest_hourly_intraday
from .disagreement_store import (
    log_daily_disagreements,
    compute_disagreement_verdict,
)
from .explainability import compute_daily_explainability
from .correlation_lab import run_intraday_delivery_correlation
from .backtest_historical import run_reduced_backtest, run_historical_per_year
from .ticket import (
    ResearchTicket,
    load_all_tickets,
    save_ticket,
    advance_ticket_state,
)

SCHEMA_FINGERPRINT = "aegis.research.platform.v1.20260731"
ENGINE_ID = "aegis.research.platform.v1"

__all__ = [
    "build_research_platform",
    "compute_runner_metrics",
    "RunnerMetrics",
    "ingest_runner1_picks_for_date",
    "ingest_runner2_picks_for_date",
    "ingest_runner2_picks_usa_for_date",
    "mark_to_market",
    "compute_head_to_head_summary",
    "ingest_runner1_intraday_picks_for_date",
    "ingest_runner2_intraday_picks_for_date",
    "fetch_hourly_bars",
    "ingest_hourly_intraday",
    "log_daily_disagreements",
    "compute_disagreement_verdict",
    "compute_daily_explainability",
    "run_intraday_delivery_correlation",
    "run_reduced_backtest",
    "run_historical_per_year",
    "ResearchTicket",
    "load_all_tickets",
    "save_ticket",
    "advance_ticket_state",
    "SCHEMA_FINGERPRINT",
    "ENGINE_ID",
]
