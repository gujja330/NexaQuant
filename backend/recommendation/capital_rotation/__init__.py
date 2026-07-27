"""backend.recommendation.capital_rotation — Capital Rotation Engine.

Wave 5 · Phase 9 · CODE BUILD (2026-07-27)

Rotate capital based on remaining-expected-upside vs alternative
opportunities. NOT time-based rotation. Decisions: EXIT · TRIM · KEEP · ADD · ROTATE.

Owner:      04_recommendation/capital_rotation (Wave 4 domain 04, Layer 5)
Inputs:     portfolio · candidates · macro_regime · sector_context
Outputs:    RotationPlan · RotationDecision[]
Schema:     aegis.capital_rotation.v1
Validator:  validation/recommendation_validation/capital_rotation_validator.py

Score formulas (Wave 5 authoritative):
    keep_score(p)      = 0.35·upside + 0.20·conf_delta + 0.15·rank_delta
                       + 0.15·sector + 0.15·pnl
    candidate_score(c) = (0.40·upside + 0.25·conf + 0.20·rank + 0.15·sector)
                       * macro_gate
    macro_gate         = {risk_on: 1.0, neutral: 0.9, risk_off: 0.5,
                          stress: 0.3, recession_warning: 0.5}
    thresholds         = {EXIT: <-0.20, TRIM_50: <+0.10, ROTATE_EDGE: >+0.25}
"""
from __future__ import annotations

from backend.recommendation.capital_rotation.engine import (  # noqa: F401
    CapitalRotationEngine,
    RotationAction,
    RotationDecision,
    RotationPlan,
    Position,
    Candidate,
    keep_score,
    candidate_score,
    macro_gate_multiplier,
    decide_action,
    compute_rotation_plan,
)

__version__ = "1.0.0"
__schema_fingerprint__ = "aegis.capital_rotation.v1.20260727"
__constitution_articles__ = ("Article 21", "Article 25", "Article 30")
