"""backend.recommendation.lifecycle — Recommendation Lifecycle state machine.

Final Platform Completion Program · Phase 2.

State machine per operator spec:
    DISCOVERED → WATCHLIST → BUY → ADD → HOLD → TRIM → EXIT → ROTATED → ARCHIVED

Every recommendation persists its full lifecycle history. Transitions are
deterministic, validated, and replayable.

Constitution: Articles 20 · 21 · 25 · 100 (L4 CONSUMED target).
"""
from __future__ import annotations

from backend.recommendation.lifecycle.state_machine import (  # noqa: F401
    RecommendationState,
    LifecycleEvent,
    LifecycleRecord,
    LifecycleTransition,
    LifecycleLedger,
    is_valid_transition,
    VALID_TRANSITIONS,
    SCHEMA_FINGERPRINT,
    SCHEMA_VERSION,
    ENGINE_ID,
)

__version__ = "1.0.0"
