"""Recommendation data types — Sprint 3."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Action(str, Enum):
    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    HOLD        = "HOLD"
    SELL        = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class Recommendation:
    """One per-ticker recommendation. This is the atomic unit downstream
    Risk / Portfolio / Learning engines consume."""
    # Identity
    market:          str
    ticker:          str
    asof:            date
    # Core call
    action:          Action
    ensemble_score:  float                    # -1..+1 from Model Factory
    raw_confidence:  float                    # ensemble confidence before adjustment
    calibrated_confidence: float              # after conflict + evidence coverage adjustment
    regime_adjusted_confidence: float         # after regime multiplier
    # Model agreement
    model_agreement: float                    # 0..1 — pct of models that agreed on sign
    disagreement_flag: bool                   # True if models materially conflict
    n_models_scoring: int                     # how many models had a view
    # Evidence
    top_models:      list[dict] = field(default_factory=list)      # [{model_id, score, weight}]
    top_features:    list[str]  = field(default_factory=list)
    # Explanation
    bull_case:       str = ""
    bear_case:       str = ""
    key_risks:       list[str] = field(default_factory=list)
    suggested_holding_period_days: int = 60
    entry_zone:      dict = field(default_factory=dict)             # {low, high, current}
    exit_conditions: list[str] = field(default_factory=list)
    # Stamps (for audit + walk-forward reconstruction)
    model_stamp:     dict = field(default_factory=dict)
    feature_set_version: str = ""
    schema_fingerprint:  str = ""


@dataclass
class RecommendationBatch:
    """One day's worth of recommendations for one market."""
    engine:         str
    version:        str
    market:         str
    asof:           date
    n_tickers:      int
    n_strong_buy:   int = 0
    n_buy:          int = 0
    n_hold:         int = 0
    n_sell:         int = 0
    n_strong_sell:  int = 0
    n_disagreement: int = 0
    recommendations: list[Recommendation] = field(default_factory=list)
    conflicts:      list[dict] = field(default_factory=list)
    notes:          list[str] = field(default_factory=list)
