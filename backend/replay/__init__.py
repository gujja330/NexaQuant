"""
Sprint 7.6 · Historical Backfill & Replay Engine.

Populates every append-only history dataset using historical raw price
data so Sprint 8 (Walk-Forward) begins with a meaningful institutional
dataset instead of waiting 60+ trading days for history to accumulate.

Free-data substrate only (yfinance / raw price parquets already on disk).
No paid APIs. No new AI agents. Deterministic per-date.
"""

from .types import (
    ReplayPlan, ReplayResult, HistoryValidation, WalkForwardReadiness,
    DataQuality, TARGET_HISTORY_FILES,
)
from .data_quality import compute_row_quality_score, quality_verdict
from .integrity import validate_history, enumerate_trading_days
from .controller import ReplayController, run_backfill

ENGINE_ID = "aegis.replay.v1"
ENGINE_VERSION = "1.0.0"

__all__ = [
    "ReplayPlan", "ReplayResult", "HistoryValidation", "WalkForwardReadiness",
    "DataQuality", "TARGET_HISTORY_FILES",
    "compute_row_quality_score", "quality_verdict",
    "validate_history", "enumerate_trading_days",
    "ReplayController", "run_backfill",
    "ENGINE_ID", "ENGINE_VERSION",
]
