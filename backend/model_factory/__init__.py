"""Model Factory — layer between Feature Intelligence and Investment Intelligence.

Owns many prediction models, evaluates them, ensembles the survivors.

Contract: every model implements BaseModel — deterministic, walk-forward-ready
(accepts a cutoff, no future rows leak). Every model stamps its outputs via
backend.model_registry so audit + walk-forward replay works.
"""
from backend.model_factory.model_base       import (                                      # noqa: F401
    BaseModel, ModelMetadata, ModelPrediction, ModelType,
)
from backend.model_factory.model_intelligence import (                                    # noqa: F401
    ModelMetrics, evaluate_model,
)
from backend.model_factory.ensemble          import (                                     # noqa: F401
    Ensemble, EnsembleWeights, ensemble_predict,
)
from backend.model_factory.factory           import (                                     # noqa: F401
    ModelFactory, list_registered_models, register_model_class,
)
