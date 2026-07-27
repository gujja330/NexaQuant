"""validation.recommendation_validation.lifecycle_validator

Phase 2 · state machine invariants. Every event chain must be a valid path.
"""
from __future__ import annotations

from backend.recommendation.lifecycle import (
    RecommendationState, VALID_TRANSITIONS, is_valid_transition,
)


def validate_ledger_dict(ledger: dict) -> tuple[bool, list[str]]:
    """Validate a serialized LifecycleLedger.to_dict()."""
    issues: list[str] = []
    if ledger.get("schema_fingerprint") != "aegis.recommendation_lifecycle.v1.20260727":
        issues.append("wrong schema_fingerprint")
    for ticker, rec in (ledger.get("records") or {}).items():
        events = rec.get("events") or []
        prev = None
        for i, e in enumerate(events):
            state_str = e.get("state")
            if state_str not in [s.value for s in RecommendationState]:
                issues.append(f"{ticker} event[{i}] unknown state: {state_str}")
                continue
            cur = RecommendationState(state_str)
            if prev is not None and not is_valid_transition(prev, cur):
                issues.append(f"{ticker} illegal transition {prev.value} -> {cur.value} at event[{i}]")
            prev = cur
    return (not issues), issues
