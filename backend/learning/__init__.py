"""Sprint 6 · Learning Engine — closes the feedback loop.

For every historical recommendation whose horizon has closed:
  1. Compute outcome (entry vs exit price) → return_pct, is_winner
  2. Feature attribution: which features drove the score
  3. Model attribution: which ensemble models contributed
  4. Failure clustering: what patterns preceded losses
  5. Confidence calibration: empirical win-rate per confidence bin

Emits an append-only learning_corpus.parquet — the substrate every
downstream sprint (Walk-Forward, AI Auditor, Research Factory) reads.

Contracts:
  - Deterministic
  - Walk-forward safe (cutoff filters historical recs to horizon_close ≤ cutoff)
  - Append-only corpus (natural key: market + ticker + rec_asof)
  - Human-in-the-loop for promotion (aegis.learning.v1 registered EXPERIMENTAL)
  - AI Learning Analyst never promotes
"""
from backend.learning.types                 import (                                        # noqa: F401
    LearningRow, Attribution, FailureCluster, CalibrationCurve, ErrorBucket,
)
from backend.learning.outcome_computer      import compute_outcomes                          # noqa: F401
from backend.learning.feature_attribution   import compute_feature_attribution               # noqa: F401
from backend.learning.model_attribution     import compute_model_attribution                 # noqa: F401
from backend.learning.failure_clustering    import cluster_failures                          # noqa: F401
from backend.learning.calibration           import fit_calibration_curve                     # noqa: F401
from backend.learning.corpus                import (                                          # noqa: F401
    read_corpus, append_corpus, corpus_path, load_recommendation_history,
)
from backend.learning.engine                import LearningEngine                           # noqa: F401
