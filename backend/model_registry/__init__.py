"""Model Registry — Sprint 2.6.

Every downstream model output (recommendation, portfolio, risk decision)
MUST stamp a model_registry entry so walk-forward + audit can reconstruct
which feature set + calibration + approval status was in effect.
"""
from backend.model_registry.registry import (                                             # noqa: F401
    register_model, stamp, get_model, list_models, ModelRecord,
    ModelStatus,
)
