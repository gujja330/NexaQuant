"""Execution Simulator data types — Sprint 7."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Fill:
    """One simulated market fill. Append-only in execution_ledger.parquet.

    Natural key: (market, ticker, fill_date, txn_id).
    """
    market:              str
    ticker:              str
    fill_date:           date
    txn_id:              str                  # unique per fill (deterministic hash)
    action:              str                  # OPEN / CLOSE / INCREASE / DECREASE
    side:                str                  # LONG / SHORT
    shares:              float                # positive absolute number
    fill_price:          float                # in market currency
    slippage_bps:        float                # signed vs mid
    commission_bps:      float
    commission_amount:   float                # in market currency
    partial_fill:        bool                 # True if part of a multi-day fill
    fill_ratio:          float                # 0..1 fraction of intended size filled today
    intended_notional:   float
    filled_notional:     float
    prior_weight:        float
    new_weight:          float
    model_stamp:         dict = field(default_factory=dict)


@dataclass
class EquityPoint:
    date:              date
    equity_value:      float               # in market currency
    cash:              float
    long_notional:     float
    short_notional:    float
    n_positions:       int
    daily_return_pct:  float = 0.0
    cumulative_return_pct: float = 0.0


@dataclass
class ExecutionState:
    """Running per-run state passed through the simulator."""
    market:            str
    starting_aum:      float                 # $ or ₹ notional
    cash:              float
    positions:         dict = field(default_factory=dict)   # ticker → {shares, weight, entry_price}


@dataclass
class ExecutionSummary:
    """One-record summary of the day's execution."""
    market:                     str
    asof:                       date
    engine_version:             str = "v1.0"
    honest_empty:               bool = False        # True when 0 trades because no upstream signal
    honest_empty_reason:        str = ""
    starting_aum:               float = 0.0
    n_trade_instructions:       int = 0             # from portfolio_diff.json (excluding HOLDs)
    n_fills_generated:          int = 0
    n_fills_partial:            int = 0
    total_commission:           float = 0.0
    total_slippage:             float = 0.0
    # Equity curve summary (this run's day)
    equity_value_end:           float = 0.0
    cash_end:                   float = 0.0
    long_notional:              float = 0.0
    short_notional:             float = 0.0
    n_open_positions:           int = 0
    n_closed_positions_today:   int = 0
    # Perf metrics (only meaningful when a curve exists — else None)
    sharpe_annualised:          float | None = None
    sortino_annualised:         float | None = None
    calmar_ratio:               float | None = None
    max_drawdown_pct:           float | None = None
    profit_factor:              float | None = None
    hit_rate:                   float | None = None
    turnover_today:             float = 0.0
    # Provenance
    model_stamp:                dict = field(default_factory=dict)
    feature_set_version:        str = ""
    schema_fingerprint:         str = ""
    notes:                      list = field(default_factory=list)
