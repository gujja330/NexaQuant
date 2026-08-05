"""Context Intelligence Layer · adapter base class.

Every context engine adapter implements this interface. Phase 2A ships
concrete adapters for Macro · Sector · Vol · News. Rest arrive in 2B/2C.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol


@dataclass
class ContextContribution:
    """Per-engine · per-recommendation contribution to adjusted confidence."""
    engine_name: str
    contribution_pts: float          # positive = boost · negative = drag
    reason: str                      # human-readable · goes into Story col
    severity: str = "info"           # info · warning · critical
    data_available: bool = True      # False = ignored in composition
    metadata: dict = field(default_factory=dict)


class ContextAdapter(Protocol):
    """Contract every context engine adapter must satisfy."""

    engine_name: str

    def contribute(self, root: Path, market: str, asof: str,
                        rec: Mapping) -> ContextContribution:
        """Return this engine's contribution for one recommendation.

        Implementations MUST be defensive: return zero-contribution +
        data_available=False when their source data is missing, never
        raise. The composer treats non-available adapters as no-ops.
        """
        ...


def zero_contribution(engine: str, reason: str) -> ContextContribution:
    """Convenience for adapters when data is unavailable."""
    return ContextContribution(
        engine_name=engine, contribution_pts=0.0,
        reason=reason, severity="info", data_available=False,
    )
