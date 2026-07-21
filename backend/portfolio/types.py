"""Portfolio Engine data types — Sprint 5."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class TradeAction(str, Enum):
    OPEN     = "OPEN"       # not in prior, now in target
    CLOSE    = "CLOSE"      # in prior, not in target
    INCREASE = "INCREASE"   # weight went up beyond rebalance threshold
    DECREASE = "DECREASE"   # weight went down beyond rebalance threshold
    HOLD     = "HOLD"       # in both, |delta| ≤ threshold


@dataclass
class Position:
    """A single portfolio holding."""
    market:          str
    ticker:          str
    weight:          float                  # signed fraction of portfolio
    notional:        float = 0.0            # in market currency (populated when AUM known)
    entry_date:      str = ""               # ISO date
    entry_price:     float | None = None
    current_price:   float | None = None
    days_held:       int = 0
    action_source:   str = ""               # e.g. "aegis.recommendation.v3"
    sector:          str = ""
    stop_loss_pct:   float | None = None
    model_stamp:     dict = field(default_factory=dict)


@dataclass
class PortfolioSnapshot:
    """One day's investable portfolio state."""
    market:              str
    asof:                date
    engine_version:      str = "v1.0"
    n_positions:         int = 0
    total_weight:        float = 0.0        # sum of long weights (0..1)
    cash_pct:            float = 0.0
    cash_reserve_target: float = 0.05       # what the policy required
    positions:           list[Position] = field(default_factory=list)
    # Diversification
    hhi:                 float = 0.0
    effective_n:         float = 0.0        # 1/HHI
    top_5_pct:           float = 0.0
    per_sector_pct:      dict = field(default_factory=dict)
    n_sectors:           int  = 0
    # Provenance
    schema_fingerprint:  str = ""
    feature_set_version: str = ""
    model_stamp:         dict = field(default_factory=dict)
    regime_at_construction: str = "unknown"
    notes:               list = field(default_factory=list)


@dataclass
class TradeInstruction:
    """One row in the rebalance diff — the trade needed to go from prior → current."""
    ticker:            str
    action:            TradeAction
    prior_weight:      float
    new_weight:        float
    delta_weight:      float
    reason:            str


@dataclass
class PortfolioDiff:
    """Full trade list to move prior → current portfolio."""
    market:          str
    asof:            date
    n_open:          int = 0
    n_close:         int = 0
    n_increase:      int = 0
    n_decrease:      int = 0
    n_hold:          int = 0
    turnover_pct:    float = 0.0            # sum |delta| / 2
    instructions:    list[TradeInstruction] = field(default_factory=list)
    rebalance_threshold_bps: int = 25
    prior_asof:      date | None = None
    notes:           list = field(default_factory=list)
