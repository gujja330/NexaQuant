"""AEGIS · Canonical delivery data model.

Every field on these dataclasses has ONE canonical source. Missing
data is represented by explicit None · never fabricated (per contract
v2 rule C4).

Identity grain (per contract v2 §Population identity):

    Registry ACTIVE           (market, position_id)
    Portfolio body (visible)  (market, position_id, runner) at asof
    Exit History body         (market, position_id, runner, closed_date)
    AEGIS History (audit)     (market, position_id, runner, snapshot_date)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Population(str, Enum):
    """Which sheet/population a canonical object belongs to."""
    CURRENT_HOLDING     = "CURRENT_HOLDING"          # visible in Portfolio · lifecycle=ACTIVE
    CURRENT_SIGNAL      = "CURRENT_SIGNAL"           # visible in Portfolio · has today's signal
    FRESH_RECOMMENDATION = "FRESH_RECOMMENDATION"    # visible in Portfolio · decision=NEW today
    SHADOW_DISCOVERY    = "SHADOW_DISCOVERY"         # visible in Portfolio · SUGGESTED · shadow-runner
    HISTORICAL_CLOSED   = "HISTORICAL_CLOSED"        # visible in Exit History
    REALIZED_ELIGIBLE   = "REALIZED_ELIGIBLE"        # subset of HISTORICAL_CLOSED · statistics
    AUDIT_OBSERVATION   = "AUDIT_OBSERVATION"        # per-snapshot row in AEGIS History


class Lifecycle(str, Enum):
    NEW    = "NEW"       # created_date == asof (genuine same-day birth)
    ACTIVE = "ACTIVE"    # holding · not born today
    CLOSED = "CLOSED"    # exited


class Decision(str, Enum):
    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    HOLD        = "HOLD"
    EXIT        = "EXIT"
    FRESH_REC   = "FRESH_REC"    # today's model produced a fresh rec for this position
    NO_SIGNAL   = "NO_SIGNAL"    # Registry-held · engine did not evaluate today
    SUGGESTED   = "SUGGESTED"    # shadow-runner discovery (research signal · not held)


@dataclass(frozen=True)
class CanonicalPosition:
    """One row in the Portfolio sheet (current populations)."""
    market:           str                  # "india" | "usa"
    position_id:      str                  # runner-inclusive · e.g. IND-R1-LUPIN-20260805-abc123
    runner:           str                  # R1 | R2 | SHADOW | MOMENTUM
    ticker:           str
    population:       Population
    lifecycle:        Lifecycle
    decision:         Decision
    entry_date:       str                  # YYYY-MM-DD
    entry_price:      Optional[float]      # None if unknown · never 0
    current_price:    Optional[float]
    days_held:        Optional[int]
    pnl_pct:          Optional[float]      # decimal · 0.05 = 5%
    sector:           Optional[str]
    stop_loss:        Optional[float]
    urgency:          Optional[str]        # HIGH | MEDIUM | LOW · None if not evaluated
    inv_quality:      Optional[str]        # QUALITY | MARGINAL | AVOID · None if not evaluated
    investability:    Optional[float]      # 0-100 · None if not scored
    action_note:      Optional[str]
    # Provenance · every field's source is recorded
    provenance:       dict = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalDecision:
    """One row in 02_Today_Decisions sheet · today's model call."""
    market:      str
    position_id: str
    runner:      str
    ticker:      str
    decision:    Decision
    confidence:  Optional[float]
    reason:      Optional[str]
    provenance:  dict = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalExit:
    """One row in 03_Exit_History_90D sheet · historical closed."""
    market:            str
    position_id:       str
    runner:            str
    ticker:            str
    population:        Population           # HISTORICAL_CLOSED or REALIZED_ELIGIBLE
    entry_date:        str
    exit_date:         str
    days_held:         int
    entry_price:       Optional[float]
    exit_price:        Optional[float]
    pnl_pct:           Optional[float]
    sector:            Optional[str]
    exit_reason:       str                  # rotation / stop_loss / target / signal / orphan / other
    is_rotation_artifact: bool = False      # |pnl| < 0.01% · excluded from statistics
    provenance:        dict = field(default_factory=dict)
