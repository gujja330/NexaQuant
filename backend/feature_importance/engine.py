"""Feature Importance Extractor · exposes top-N features per rec.

Deterministic. Reads Runner 2 v3 rec output's `top_features` +
`top_models`, ranks them, and emits a per-rec attribution payload.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.feature_importance.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.feature_importance.v1"

TOP_N_FEATURES_DEFAULT = 20


@dataclass(frozen=True)
class FeatureAttribution:
    ticker: str
    top_features: list[str]
    top_models: list[dict]     # [{model_id, score}]
    n_features_reported: int
    n_models_reported: int
    coverage_gap: str          # NONE · PARTIAL · FULL
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


class FeatureImportanceEngine:

    def __init__(self, top_n: int = TOP_N_FEATURES_DEFAULT):
        self.top_n = top_n

    def extract(self, recs: Sequence[Mapping]) -> list[FeatureAttribution]:
        out = []
        for r in recs:
            features = list(r.get("top_features") or [])[:self.top_n]
            models = list(r.get("top_models") or [])[:self.top_n]
            gap = self._coverage_gap(features)
            out.append(FeatureAttribution(
                ticker=r.get("ticker", ""),
                top_features=features,
                top_models=models,
                n_features_reported=len(features),
                n_models_reported=len(models),
                coverage_gap=gap,
            ))
        return out

    def _coverage_gap(self, features) -> str:
        if not features: return "FULL"
        if len(features) < 5: return "PARTIAL"
        return "NONE"


def extract_importance(recs: Sequence[Mapping], top_n: int = TOP_N_FEATURES_DEFAULT) -> list[dict]:
    return [asdict(a) for a in FeatureImportanceEngine(top_n).extract(recs)]
