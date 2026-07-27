"""backend.recommendation.dynamic_holding — Dynamic Holding Engine.

Final Platform Completion Program · Phase 4.

Replaces static "30/60/90 days" logic with a composite that adapts to:
    confidence decay · expected alpha remaining · sector strength · macro
    regime · rotation score · portfolio overlap · opportunity cost · risk ·
    volatility · liquidity · benchmark alpha.

Deterministic. Every input maps to a bounded contribution. Composite
holding_days is monotonic in the reasons documented in the operator spec.
"""
from __future__ import annotations

from backend.recommendation.dynamic_holding.engine import (  # noqa: F401
    DynamicHoldingEngine,
    HoldingDecision,
    compute_holding_days,
    SCHEMA_FINGERPRINT,
    SCHEMA_VERSION,
    ENGINE_ID,
)

__version__ = "1.0.0"
