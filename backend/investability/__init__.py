"""AEGIS Investability Engine · Wave 1 MVP.

Full spec: Sprint K+ Part 26 (`docs/AEGIS_SPRINT_K_PLUS_LOCKED.md`).

Answers: "Should we own this stock AT ALL?" (structural quality)
Distinct from: Runner 2's Opportunity Score ("Is this stock attractive TODAY?")

Wave 1 MVP (this week · data we already have):
    Fundamental (25%)  · yfinance ticker.info
    Technical (20%)    · parquet-based indicators
    Liquidity (5%)     · bhavcopy delivery % + volume
    Governance-lite (15%) · yfinance-derivable signals · placeholder for full

Wave 2 (Sprint K Part 26 · Nov 11-17):
    Ownership (10%)    · shareholding-pattern data source
    Sector (10%)       · existing sector_report + rotation
    Macro (5%)         · existing macro engine
    News/Event (5%)    · impact-classified news feed
    Earnings (5%)      · earnings calendar + estimates
"""
from backend.investability.scorer import (
    score_ticker,
    score_universe,
    Investability,
    THRESHOLD_REJECT,
    THRESHOLD_HOLD,
    THRESHOLD_BUY,
    THRESHOLD_STRONG_BUY,
)

__all__ = [
    "score_ticker",
    "score_universe",
    "Investability",
    "THRESHOLD_REJECT",
    "THRESHOLD_HOLD",
    "THRESHOLD_BUY",
    "THRESHOLD_STRONG_BUY",
]
