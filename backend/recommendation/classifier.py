"""Classifier — turn (score, calibrated_confidence, disagreement) into an Action.

Deterministic decision boundaries. Sprint 3 baseline; Sprint 9's Learning
Engine may propose calibrated thresholds via a promotion gate later.
"""
from __future__ import annotations

from backend.recommendation.types import Action


# Wave Y · dead code `_MATRIX` removed (Red Team G4 · v2.2 S7).
# Actual decision logic lives in the if-else chain in `classify()` below.


def classify(score: float, calibrated_confidence: float,
              disagreement_flag: bool) -> Action:
    """Baseline classifier. When disagreement_flag is True the call collapses to HOLD."""
    if disagreement_flag:
        return Action.HOLD

    s = max(-1.0, min(1.0, score))
    c = max(0.0, min(1.0, calibrated_confidence))

    if s >= 0.50 and c >= 0.70:      return Action.STRONG_BUY
    if s >= 0.20 and c >= 0.50:      return Action.BUY
    if s <= -0.50 and c >= 0.70:     return Action.STRONG_SELL
    if s <= -0.20 and c >= 0.50:     return Action.SELL
    return Action.HOLD
