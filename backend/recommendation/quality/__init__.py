"""backend.recommendation.quality — Recommendation Quality Engine.

Enterprise Completion Program · Phase D.

Instead of just an action label, every rec answers:
    expected_alpha_pct         · point estimate
    expected_alpha_ci_low      · 95% confidence low
    expected_alpha_ci_high     · 95% confidence high
    downside_risk_pct          · worst-case scenario
    win_probability            · [0, 1]
    expected_holding_horizon   · days (from Dynamic Holding Engine)
    entry_confidence           · [0, 1]
    exit_confidence            · [0, 1]
    recommendation_stability   · variance of last N days' actions
    recommendation_decay       · confidence drop-off rate

Deterministic · fingerprinted · walk-forward safe.
"""
from __future__ import annotations

from backend.recommendation.quality.engine import (  # noqa: F401
    QualityEngine,
    QualityScore,
    compute_quality,
    SCHEMA_FINGERPRINT,
    SCHEMA_VERSION,
    ENGINE_ID,
)

__version__ = "1.0.0"
