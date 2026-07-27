"""backend.recommendation.delta — Recommendation Delta Engine.

Final Platform Completion Program · Phase 3.

For every rec today, compute deltas against yesterday's snapshot:
  previous_rank · current_rank · rank_delta
  confidence_delta · technical_delta · fundamental_delta · macro_delta
  sector_delta · risk_delta · rotation_delta
  reason_for_change · ai_explanation

Deterministic. Given identical (today, yesterday) inputs → identical deltas.
"""
from __future__ import annotations

from backend.recommendation.delta.engine import (  # noqa: F401
    DeltaEngine,
    RecommendationDelta,
    compute_deltas,
    SCHEMA_FINGERPRINT,
    SCHEMA_VERSION,
    ENGINE_ID,
)

__version__ = "1.0.0"
