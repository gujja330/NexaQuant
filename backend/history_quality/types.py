"""Sprint B0 · History Quality Validation types."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional


class FamilyStatus(str, Enum):
    """Per-family verdict."""
    PASS         = "PASS"
    WARN         = "WARN"
    FAIL         = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"    # family expected but not yet populated (e.g. execution_history)


class HistoryFamily(str, Enum):
    """The data families B0 validates."""
    RECOMMENDATION       = "recommendation"
    RECOMMENDATION_RUNNER1 = "recommendation_runner1"
    RISK                 = "risk"
    PORTFOLIO            = "portfolio"
    EXECUTION            = "execution"
    LEARNING             = "learning"
    LEARNING_CORPUS      = "learning_corpus"
    MACRO                = "macro"
    FACTOR_LIBRARY       = "factor_library"
    PRICE                = "price"                # raw ticker parquets


class ReadinessVerdict(str, Enum):
    """Aggregate verdict — gates Sprint B1 replay."""
    READY_FOR_REPLAY = "READY_FOR_REPLAY"
    PARTIAL          = "PARTIAL"                  # can run limited replay with WARN downgrades
    NEEDS_REPAIR     = "NEEDS_REPAIR"             # must fix before B1


@dataclass(frozen=True)
class FamilyCheckResult:
    """Per-family check output."""
    family: str
    file_path: str
    exists: bool
    status: str                                   # FamilyStatus value
    n_rows: int = 0
    n_unique_dates: int = 0
    n_duplicate_dates: int = 0
    n_missing_trading_days: int = 0
    date_range: Optional[str] = None
    schema_ok: bool = True
    schema_issues: List[str] = field(default_factory=list)
    quality_score: int = 0                        # 0..100 (see metrics.py)
    notes: List[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """Aggregate quality report for a market."""
    engine: str
    version: str
    market: str
    run_utc: str
    verdict: str                                  # ReadinessVerdict value
    n_families_checked: int
    n_pass: int
    n_warn: int
    n_fail: int
    n_not_applicable: int
    overall_quality_score: int
    per_family: List[FamilyCheckResult] = field(default_factory=list)
    corporate_action_flags: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
