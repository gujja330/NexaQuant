"""Sector Rotation Model — pick tickers whose sector is currently leading."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class SectorRotationModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.sector_rotation.v1", model_type=ModelType.SECTOR_ROTATION,
        version="1.0.0", algorithm="weighted_rule_v1",
        feature_dependencies=["sector_return_1m_pct", "sector_is_leader", "sector_is_laggard"],
        business_rationale=("Capital rotates between sectors over 3-12 month cycles. "
                             "Riding leadership beats fighting it."),
        economic_intuition=("Institutional flows chase performance; sector momentum "
                             "persists longer than individual stock momentum."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        sr  = df.get("sector_return_1m_pct", pd.Series([None] * len(df))).astype(float)
        lead = df.get("sector_is_leader", pd.Series([None] * len(df))).astype(float).fillna(0)
        lag  = df.get("sector_is_laggard", pd.Series([None] * len(df))).astype(float).fillna(0)
        composite = 0.6 * rank_score(sr) + 0.3 * lead - 0.1 * lag
        conf = pd.Series(sr.notna().astype(float), index=df.index)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"sector_return_1m={s}·leader={l}" for s, l in zip(sr, lead)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
