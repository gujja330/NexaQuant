"""Sprint 7.5 · Factor Library — types."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FactorReading:
    """One row of the factor library: value + delta + trend for a single factor on a single date."""
    asof: date
    market: str
    factor: str                    # e.g. "oil_wti", "vix", "us_10y"
    source: str                    # e.g. "commodity", "currency", "bond", "volatility", "central_bank", "derived", "rotation"
    unit: str                      # "pct" | "bps" | "index" | "ratio" | "flag" | "rate" | "label"
    value: Optional[float] = None
    value_label: Optional[str] = None      # for categorical factors (rate_cycle, sector_rotation_leader)
    change_1d: Optional[float] = None
    change_1w: Optional[float] = None
    change_1m: Optional[float] = None
    trend: Optional[str] = None            # "bull" | "bear" | "sideways" | None
    confidence: float = 1.0
    affected_sectors: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class FactorLibraryResult:
    """Full output of one Factor Library run."""
    engine: str
    version: str
    market: str
    asof: date
    n_factors: int
    factors: List[FactorReading]
    model_stamp: Dict[str, Any] = field(default_factory=dict)
