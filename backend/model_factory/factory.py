"""ModelFactory — orchestrates training + prediction across all registered models."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from backend.model_factory.model_base import BaseModel, ModelPrediction
from backend.model_factory.models     import ALL_MODELS
from backend.model_factory.models.ai_hybrid import AIHybridModel


_REGISTRY: list[type[BaseModel]] = list(ALL_MODELS)


def register_model_class(cls: type[BaseModel]) -> None:
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)


def list_registered_models() -> list[type[BaseModel]]:
    return list(_REGISTRY)


class ModelFactory:
    def __init__(self, repo_root: Path, market: str):
        self.repo_root = Path(repo_root)
        self.market = market
        self.models: list[BaseModel] = [cls() for cls in _REGISTRY]

    def train_all(self, features: pd.DataFrame, target: pd.Series | None,
                    cutoff: date) -> None:
        for m in self.models:
            m.train(features, target, cutoff)

    def predict_all(self, features: pd.DataFrame, cutoff: date) -> list[ModelPrediction]:
        """Predict from every model. AI Hybrid model gets the OTHER models'
        predictions injected before running (meta-model)."""
        primary: list[ModelPrediction] = []
        hybrid: AIHybridModel | None = None
        for m in self.models:
            if isinstance(m, AIHybridModel):
                hybrid = m
                continue
            primary.append(m.predict(features, cutoff))
        if hybrid is not None:
            hybrid.set_component_predictions(primary)
            primary.append(hybrid.predict(features, cutoff))
        return primary

    def describe_all(self) -> list[dict]:
        return [m.describe() for m in self.models]
