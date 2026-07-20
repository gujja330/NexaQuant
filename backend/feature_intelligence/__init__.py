"""Feature Intelligence — MLOps layer above Feature Store.

Governs feature lifecycle: quality, drift, importance, selection, evolution,
promotion. Only ACTIVE features flow to downstream engines.

Determinism: every engine is a pure function of the current snapshot +
optionally the history of prior snapshots. No LLM calls, no randomness.
Walk-forward safe.
"""
from backend.feature_intelligence.governance   import (                                     # noqa: F401
    validate_governance, GovernanceResult,
)
from backend.feature_intelligence.quality      import (                                     # noqa: F401
    persist_quality_snapshot, load_quality_history, QualitySnapshot,
)
from backend.feature_intelligence.drift        import (                                     # noqa: F401
    detect_drift, DriftReport, psi, js_divergence, ks_statistic,
)
from backend.feature_intelligence.importance   import (                                     # noqa: F401
    compute_importance, ImportanceResult,
)
from backend.feature_intelligence.selection    import (                                     # noqa: F401
    select_features, SelectionResult,
)
from backend.feature_intelligence.evolution    import (                                     # noqa: F401
    propose_candidate, evaluate_candidate, CandidateFeature,
)
