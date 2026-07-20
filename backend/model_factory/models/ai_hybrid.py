"""AI Hybrid Model — meta-learner that ensembles the top-K models by their
own walk-forward performance (when Sprint 9 fills WF metrics; equal-weight
until then).

Sprint 2.7 behavior: with no WF metrics yet, this model just averages the
predictions of the other 10 registered models. Later sprints will up-weight
models with proven regime-adjusted alpha.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType,
)


class AIHybridModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.ai_hybrid.v1", model_type=ModelType.AI_HYBRID, version="1.0.0",
        algorithm="ensemble_meta",
        feature_dependencies=[],       # depends on OTHER MODELS' outputs, not features directly
        business_rationale=("No single style wins in every regime. A meta-model that "
                             "trusts each style according to its recent walk-forward "
                             "accuracy adapts without over-fitting one lens."),
        economic_intuition=("Ensembles reduce single-model idiosyncratic risk; the WF-"
                             "weighted variant tilts toward the styles the market is "
                             "currently paying for."),
        approval_status="EXPERIMENTAL",
    )

    def __init__(self):
        super().__init__()
        self._other_predictions: list[ModelPrediction] = []

    def set_component_predictions(self, preds: list[ModelPrediction]) -> None:
        """The runner injects other models' predictions before calling predict()."""
        self._other_predictions = [p for p in preds if p.model_id != self.metadata.model_id]

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        if not self._other_predictions:
            # No components → zero score
            df = features.copy()
            preds = pd.DataFrame({
                "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
                "score":      0.0, "confidence": 0.0,
                "evidence":   ["no component models attached"] * len(df),
            }).reset_index(drop=True)
            return ModelPrediction(
                model_id=self.metadata.model_id,
                market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
                asof=cutoff, predictions=preds, n_scored=int(len(preds)),
                notes=["hybrid model needs component predictions"],
            )

        # Simple weighted mean by per-model confidence
        all_scores: dict[str, list[float]] = {}
        all_confs:  dict[str, list[float]] = {}
        for p in self._other_predictions:
            for _, r in p.predictions.iterrows():
                t = str(r["ticker"])
                all_scores.setdefault(t, []).append(float(r["score"]))
                all_confs.setdefault(t, []).append(float(r["confidence"]))

        rows = []
        for t, scores in all_scores.items():
            confs = all_confs[t]
            wsum  = sum(s * c for s, c in zip(scores, confs))
            csum  = sum(confs)
            score = wsum / csum if csum > 0 else 0.0
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            rows.append({"ticker": t,
                          "score": max(-1.0, min(1.0, score)),
                          "confidence": avg_conf,
                          "evidence": f"ensemble of {len(scores)} component models"})
        preds = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(features["market"].iloc[0]) if "market" in features.columns and len(features) else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
            notes=[f"WF-weighted ensemble deferred; equal-weight over {len(self._other_predictions)} models"],
        )
