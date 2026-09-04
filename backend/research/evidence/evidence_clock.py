"""Section G · Evidence Clock (measurement layer · NOT governance).

Six states · distinguished mechanically · NOT collapsed:

    DATA_EXISTS  →  DATA_USABLE  →  HISTORICAL_TESTED  →  OOS_TESTED
                        ↓                                       ↓
                  FORWARD_RUNNING  ← ← ← ← ← ← ← ← ← ← ← ← ←
                        ↓
                  FORWARD_VALIDATED

13-stage Coverage Tracker remains the canonical governance state machine.
This clock is a per-item evidence-measurement layer only. Two views · one truth.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime


STATES = (
    "DATA_EXISTS",
    "DATA_USABLE",
    "HISTORICAL_TESTED",
    "OOS_TESTED",
    "FORWARD_RUNNING",
    "FORWARD_VALIDATED",
)


@dataclass
class EvidenceClock:
    item_id: str
    market: str
    historical_n: int = 0
    historical_oos_n: int = 0
    forward_n: int = 0
    forward_matured_n: int = 0
    oldest_pit_date: str | None = None
    latest_pit_date: str | None = None
    oldest_forward_date: str | None = None
    latest_forward_date: str | None = None
    fold_count: int = 0
    trial_count: int = 0
    statistical_status: str = "not_run"
    forward_status: str = "not_started"
    state: str = "DATA_EXISTS"
    last_updated_utc: str = ""

    def derive_state(self) -> str:
        """Compute state from field values · mechanical · never a judgment call."""
        if self.historical_n <= 0:
            return "DATA_EXISTS"
        if self.oldest_pit_date is None or self.fold_count == 0:
            return "DATA_USABLE"
        if self.historical_oos_n <= 0:
            return "HISTORICAL_TESTED"
        if self.forward_n <= 0:
            return "OOS_TESTED"
        if self.forward_matured_n <= 0:
            return "FORWARD_RUNNING"
        if self.statistical_status == "passed" and self.forward_status == "validated":
            return "FORWARD_VALIDATED"
        return "FORWARD_RUNNING"

    def tick(self) -> None:
        """Recompute state + last_updated_utc from current field values."""
        self.state = self.derive_state()
        self.last_updated_utc = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_dict(self) -> dict:
        return asdict(self)


def coverage_tracker_projection(state: str) -> str:
    """Project 6-state evidence clock into 13-stage Coverage Tracker for
    unified dashboard display. Tracker remains the source of truth · this
    is a view-only projection."""
    mapping = {
        "DATA_EXISTS":       "Data-required",
        "DATA_USABLE":       "PIT-ready",
        "HISTORICAL_TESTED": "Tested",
        "OOS_TESTED":        "OOS",
        "FORWARD_RUNNING":   "Paper",
        "FORWARD_VALIDATED": "Shadow",
    }
    return mapping.get(state, "Mapped")
