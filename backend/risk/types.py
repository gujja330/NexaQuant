"""Risk Engine data types — Sprint 4."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class CapReason(str, Enum):
    """Which constraint bounded the final position size."""
    KELLY            = "kelly"
    PER_TICKER_CAP   = "per_ticker_cap"
    SECTOR_CAP       = "sector_cap"
    VOL_CAP          = "vol_cap"
    CONFIDENCE_GATE  = "confidence_gate"
    DISAGREEMENT     = "disagreement"
    SHORT_DISABLED   = "short_disabled"
    NOT_CAPPED       = "not_capped"


@dataclass
class RiskBudget:
    """Per-market risk configuration loaded from configs/risk_budget.yaml."""
    market:                str
    max_kelly_fraction:    float             # cap on theoretical Kelly (e.g. 0.25)
    per_ticker_cap:        float             # max weight per ticker (e.g. 0.06)
    per_sector_cap:        float             # max weight per sector (e.g. 0.25)
    target_portfolio_vol:  float             # annualised (e.g. 0.15)
    enable_shorts:         bool
    default_stop_loss_pct: float             # e.g. -0.08
    confidence_tier_mult:  dict              # {STRONG_BUY: 1.0, BUY: 0.6, SELL: -0.6, STRONG_SELL: -1.0}


@dataclass
class SizedPosition:
    """One per BUY/SELL recommendation after risk sizing. HOLD recs are dropped."""
    market:              str
    ticker:              str
    action:              str                 # STRONG_BUY | BUY | SELL | STRONG_SELL
    ensemble_score:      float
    confidence:          float               # regime_adjusted from Sprint 3
    target_weight:       float               # signed fraction of portfolio [-cap, +cap]
    target_notional:     float               # in market currency (0 if unknown budget)
    risk_budget_bps:     float               # bps of portfolio risk consumed
    stop_loss_pct:       float               # e.g. -0.08 for -8%
    take_profit_pct:     float | None
    vol_20d_annualised:  float
    kelly_fraction:      float               # theoretical Kelly (before capping)
    cap_reason:          CapReason           # which constraint bounded final size
    entry_reference:     float | None        # current price for stop/profit reference
    model_stamp:         dict = field(default_factory=dict)
    schema_fingerprint:  str  = ""
    feature_set_version: str  = ""


@dataclass
class RiskReport:
    """Portfolio-level risk aggregation. Emitted alongside sized_positions."""
    market:                     str
    asof:                       date
    engine_version:             str  = "v1.0"
    regime:                     str  = "unknown"
    n_positions:                int  = 0
    n_long:                     int  = 0
    n_short:                    int  = 0
    total_long_exposure_pct:    float = 0.0
    total_short_exposure_pct:   float = 0.0
    gross_exposure_pct:         float = 0.0
    net_exposure_pct:           float = 0.0
    cash_pct:                   float = 0.0
    hhi_concentration:          float = 0.0        # 0..1
    top_5_concentration_pct:    float = 0.0
    per_sector_exposure_pct:    dict = field(default_factory=dict)
    portfolio_var_95_1d_pct:    float = 0.0        # 1-day 95% VaR as % of portfolio
    portfolio_cvar_95_1d_pct:   float = 0.0
    portfolio_vol_annualised:   float = 0.0
    verdict:                    str  = "PASS"      # PASS | WARNING | FAIL
    breaches:                   list = field(default_factory=list)
    notes:                      list = field(default_factory=list)
