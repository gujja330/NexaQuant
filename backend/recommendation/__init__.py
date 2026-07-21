"""Recommendation Intelligence Engine v1.0 — Sprint 3.

Layer between the Model Factory ensemble and Risk/Portfolio engines.
Converts a per-ticker ensemble score into an actionable recommendation
(STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL) with full evidence,
bull/bear cases, key risks, entry zone, and exit conditions.

**Legacy separation:** `research/adaptive_rec_v2/` is UNTOUCHED. This is
the NEW engine at `backend/recommendation/`. Downstream sprints (Risk,
Portfolio, Learning) consume this engine's output at
`{market}/reports/recommendations_v3.json`.

Contracts:
  - Deterministic (same inputs + cutoff → identical output)
  - Walk-forward ready (accepts cutoff, no future data used)
  - No LLM calls (template-driven; upgrade via determinism="llm-cached")
  - Human-in-the-loop (engine outputs marked EXPERIMENTAL; promotion
    requires backend.promotion.promotion_gate.approve_model)
"""
from backend.recommendation.types       import (                                          # noqa: F401
    Recommendation, Action, RecommendationBatch,
)
from backend.recommendation.engine      import RecommendationEngine                        # noqa: F401
from backend.recommendation.conflict    import resolve_conflict, ConflictReport            # noqa: F401
from backend.recommendation.calibration import calibrate_confidence, CalibrationInputs     # noqa: F401
from backend.recommendation.regime_adjust import apply_regime_adjustment                    # noqa: F401
from backend.recommendation.classifier  import classify                                     # noqa: F401
from backend.recommendation.explainer   import explain                                     # noqa: F401
