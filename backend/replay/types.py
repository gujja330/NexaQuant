"""Sprint 7.6 · Replay engine types."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


# The seven append-only history parquets Sprint 7.5 established. Sprint 7.6
# backfills the ones that CAN be computed from existing raw data; the ones
# requiring live-runner replay are marked as deferred.
TARGET_HISTORY_FILES = {
    "macro_history":            {"backfillable": True,  "requires_data": "macro raw prices (yfinance)"},
    "factor_library_history":   {"backfillable": True,  "requires_data": "macro_history"},
    "learning_history":         {"backfillable": True,  "requires_data": "recommendation_history + raw prices"},
    "recommendation_history":   {"backfillable": False, "requires_data": "runner --asof refactor (Sprint 7.7)"},
    "risk_history":             {"backfillable": False, "requires_data": "recommendation_history + runner --asof (Sprint 7.7)"},
    "portfolio_history":        {"backfillable": False, "requires_data": "risk_history + runner --asof (Sprint 7.7)"},
    "execution_history":        {"backfillable": False, "requires_data": "portfolio_history + runner --asof (Sprint 7.7)"},
}


@dataclass(frozen=True)
class DataQuality:
    """Per-row data quality attribution."""
    score: int                          # 0-100
    completeness: float                 # fraction of expected fields present (0-1)
    freshness_days_before_asof: int     # 0 = same-day, higher = staler input
    source_count: int                   # how many raw sources contributed
    verdict: str                        # "high" | "medium" | "low" | "unusable"
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReplayPlan:
    market: str                         # "india" | "usa"
    date_from: date
    date_to: date
    steps: List[str] = field(default_factory=list)   # ["features", "macro", "factor_library", "learning"]
    resume: bool = True
    parallel: int = 1                   # workers (>=1; sequential if 1)


@dataclass
class ReplayResult:
    market: str
    date_from: date
    date_to: date
    n_trading_days: int
    step_results: Dict[str, Dict[str, Any]]           # {"features": {"n_ok": 42, "n_skipped": 3, ...}, ...}
    integrity: Optional[Dict[str, Any]] = None
    walk_forward_readiness: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryValidation:
    file: str                             # e.g. "reports/macro_history.parquet"
    market: str
    n_rows: int
    n_unique_dates: int
    n_missing_trading_days: int
    n_duplicate_dates: int
    schema_ok: bool
    schema_notes: List[str] = field(default_factory=list)
    date_range: Optional[str] = None      # "2021-07-19..2026-07-21"
    verdict: str = "PASS"                 # "PASS" | "WARN" | "FAIL"


@dataclass(frozen=True)
class WalkForwardReadiness:
    market: str
    historical_days: int
    recommendation_rows: int
    execution_rows: int
    learning_corpus_rows: int
    factor_library_rows: int
    macro_history_rows: int
    missing_dates: int
    duplicate_dates: int
    data_quality_score_avg: float
    verdict: str                          # "READY" | "PARTIAL" | "NOT_READY"
    notes: List[str] = field(default_factory=list)
