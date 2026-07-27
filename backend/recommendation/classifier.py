"""Classifier — turn (score, calibrated_confidence, disagreement) into an Action.

Deterministic decision boundaries. Sprint 3 baseline; Sprint 9's Learning
Engine may propose calibrated thresholds via a promotion gate later.
"""
from __future__ import annotations

from backend.recommendation.types import Action


# Wave Y · dead code `_MATRIX` removed (Red Team G4 · v2.2 S7).
# Actual decision logic lives in the if-else chain in `classify()` below.

# Institutional Completion Program · signal-substrate thresholds.
# Below these bounds the ensemble has effectively-zero signal · returning HOLD
# would be dishonest (it implies "we chose to hold"). Emit INSUFFICIENT_DATA
# so downstream (dashboard · Telegram · reports) can distinguish "no decision
# possible with current data" from "genuine HOLD".
_MIN_SIGNAL_SCORE = 0.001
_MIN_SIGNAL_CONFIDENCE = 0.01


def classify(score: float, calibrated_confidence: float,
              disagreement_flag: bool) -> Action:
    """Baseline classifier.

    Order of decision:
      1. If score AND confidence are both effectively zero → INSUFFICIENT_DATA
         (honest institutional signal · data substrate is depleted)
      2. If disagreement_flag → HOLD (safety valve · models genuinely disagree)
      3. Otherwise threshold matrix (STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL)
    """
    s = max(-1.0, min(1.0, score))
    c = max(0.0, min(1.0, calibrated_confidence))

    # Rule 1 · insufficient signal: substrate too thin for any decision
    if abs(s) < _MIN_SIGNAL_SCORE and c < _MIN_SIGNAL_CONFIDENCE:
        return Action.INSUFFICIENT_DATA

    # Rule 2 · genuine disagreement · safety HOLD
    if disagreement_flag:
        return Action.HOLD

    # Rule 3 · threshold matrix
    if s >= 0.50 and c >= 0.70:      return Action.STRONG_BUY
    if s >= 0.20 and c >= 0.50:      return Action.BUY
    if s <= -0.50 and c >= 0.70:     return Action.STRONG_SELL
    if s <= -0.20 and c >= 0.50:     return Action.SELL
    return Action.HOLD
