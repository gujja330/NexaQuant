"""backend.feature_importance — Feature Importance Extractor.

Enterprise Completion Program · Phase I.

For every rec, extract the top-N features that drove it — from the
ensemble output's `top_models[]` and `top_features[]` fields. SHAP-like
attribution is deferred until the substrate provides non-zero scores;
this engine currently provides the deterministic feed-through + ranking.
"""
from __future__ import annotations

from backend.feature_importance.engine import (  # noqa: F401
    FeatureImportanceEngine,
    FeatureAttribution,
    extract_importance,
    SCHEMA_FINGERPRINT, SCHEMA_VERSION, ENGINE_ID,
)

__version__ = "1.0.0"
