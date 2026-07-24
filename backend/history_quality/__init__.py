"""
Sprint B0 · History Quality Validation.

Validates that history is actually complete BEFORE Sprint B1 (replay) starts.
Prevents Replay from silently training on incomplete data.

Per-family checks:
- Recommendation history (missing/duplicate/partial/corrupted days)
- Price history (trading-day gaps, missing candles, corporate-action anomalies, delistings)
- Macro (observation coverage)
- Commodities (Gold/Oil/Copper/Nat-Gas coverage)
- News (coverage, duplicates)
- Learning corpus (continuous or broken)

Emits reports/history_quality_report.json (per market) with
verdict: READY_FOR_REPLAY | NEEDS_REPAIR.

Design (per Phase 5 Engine Implementation Standard):
    types.py         · dataclasses / enums / verdicts
    validators.py    · per-family check functions (pure)
    engine.py        · orchestrator that runs all validators
    persistence.py   · report writer (JSON + parquet + markdown)
    comparison.py    · cross-market comparison builder
    metrics.py       · quality-score computation
    exceptions.py    · engine-specific exceptions
    config.py        · threshold loader
    utils.py         · pure helpers
"""

from .engine import HistoryQualityEngine, run_quality_check
from .types import (
    FamilyStatus, HistoryFamily, FamilyCheckResult, QualityReport,
    ReadinessVerdict,
)
from .comparison import build_comparison

ENGINE_ID = "aegis.history_quality.v1"
ENGINE_VERSION = "1.0.0"

__all__ = [
    "HistoryQualityEngine", "run_quality_check",
    "FamilyStatus", "HistoryFamily", "FamilyCheckResult",
    "QualityReport", "ReadinessVerdict",
    "build_comparison",
    "ENGINE_ID", "ENGINE_VERSION",
]
