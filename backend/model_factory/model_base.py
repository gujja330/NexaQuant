"""BaseModel — the interface every prediction model in AEGIS implements.

Walk-forward contract:
  - train(features, target, cutoff) must NOT use rows with date > cutoff
  - predict(features, cutoff) must be deterministic on identical features
  - describe() returns metadata for the registry
  - save/load are serialisation hooks (JSON is fine for rule-based models)

Sprint 2.7 ships rule-based scoring models (no ML training) because the
Feature Store has only one snapshot today. When Sprint 9's Learning Engine
accumulates history, the same interface plugs into ML training without
changes to downstream consumers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import ClassVar

import pandas as pd


class ModelType(str, Enum):
    MOMENTUM       = "momentum"
    TREND          = "trend"
    VALUE          = "value"
    GROWTH         = "growth"
    QUALITY        = "quality"
    MEAN_REVERSION = "mean_reversion"
    NEWS           = "news"
    MACRO          = "macro"
    SECTOR_ROTATION = "sector_rotation"
    EVENT_DRIVEN   = "event_driven"
    AI_HYBRID      = "ai_hybrid"


@dataclass
class ModelMetadata:
    """Full registry record for a model. Persisted via backend.model_registry."""
    model_id:             str                  # e.g. "aegis.momentum.v1"
    model_type:           ModelType
    version:              str
    algorithm:            str                  # "weighted_rule_v1" | "lightgbm" | ...
    feature_dependencies: list[str] = field(default_factory=list)
    business_rationale:   str = ""
    economic_intuition:   str = ""
    owner:                str = "aegis-core"
    training_window:      str = "since inception"      # human-readable
    walk_forward_metrics: dict = field(default_factory=dict)
    calibration_version:  str = ""
    schema_version:       str = ""
    approval_status:      str = "EXPERIMENTAL"        # EXPERIMENTAL | APPROVED | DEPRECATED
    created:              str = ""
    last_updated:         str = ""


@dataclass
class ModelPrediction:
    """The output shape every model must return from `predict()`.

    Per ticker: a score in [-1, +1] with a confidence in [0, 1] plus per-feature
    evidence for the AI Model Analyst.
    """
    model_id:    str
    market:      str
    asof:        date
    predictions: pd.DataFrame                  # columns: ticker, score, confidence, evidence
    n_scored:    int
    notes:       list[str] = field(default_factory=list)


class BaseModel(ABC):
    """Every model in the Factory extends this."""

    METADATA: ClassVar[ModelMetadata]

    def __init__(self):
        self.metadata: ModelMetadata = self.METADATA
        self.state: dict = {}

    @abstractmethod
    def train(self, features: pd.DataFrame, target: pd.Series | None,
                cutoff: date) -> None:
        """Fit on features observable at cutoff. May be a no-op for rule-based models."""

    @abstractmethod
    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        """Score every row in features. Deterministic on identical input."""

    def describe(self) -> dict:
        return {
            "model_id": self.metadata.model_id,
            "type":     self.metadata.model_type.value,
            "version":  self.metadata.version,
            "algorithm": self.metadata.algorithm,
            "features_used": list(self.metadata.feature_dependencies),
            "business_rationale": self.metadata.business_rationale,
            "economic_intuition": self.metadata.economic_intuition,
            "approval_status": self.metadata.approval_status,
        }

    def save(self) -> dict:
        """Return a serialisable state dict. Rule-based models return {} — nothing to save."""
        return dict(self.state)

    def load(self, state: dict) -> None:
        self.state = dict(state or {})


# ─── Helper: normalise a raw signal to [-1, +1] via rank ────────
def rank_score(s: pd.Series) -> pd.Series:
    """Convert an arbitrary signal to [-1, +1] by cross-sectional rank."""
    s = s.astype(float)
    n = len(s.dropna())
    if n < 2:
        return pd.Series([0.0] * len(s), index=s.index)
    ranks = s.rank(method="average", pct=True)
    return (2.0 * ranks - 1.0).fillna(0.0)


def zscore(s: pd.Series) -> pd.Series:
    """Standard-normal z-score. NaN-safe."""
    s = s.astype(float)
    mu = s.mean(); sig = s.std()
    if pd.isna(sig) or sig == 0:
        return pd.Series([0.0] * len(s), index=s.index)
    return ((s - mu) / sig).fillna(0.0)
