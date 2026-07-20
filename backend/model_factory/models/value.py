"""Value Model — 1/PE + 1/PB + inverse quality-cost."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class ValueModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.value.v1", model_type=ModelType.VALUE, version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=["fund_trailing_pe", "fund_price_to_book"],
        business_rationale=("Buying below fair value creates a margin of safety; "
                             "reversion-to-mean historically rewards cheap stocks over "
                             "expensive ones across long horizons."),
        economic_intuition=("Overreaction to bad news creates persistent under-pricing "
                             "in fundamentally sound companies; value is the correction."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        # Invert PE and PB (lower PE = higher value score)
        pe = df.get("fund_trailing_pe", pd.Series([None] * len(df)))
        pb = df.get("fund_price_to_book", pd.Series([None] * len(df)))
        inv_pe = 1.0 / pe.replace(0, pd.NA).astype(float)
        inv_pb = 1.0 / pb.replace(0, pd.NA).astype(float)
        composite = 0.6 * rank_score(inv_pe) + 0.4 * rank_score(inv_pb)
        conf = pd.Series((pe.notna().astype(float) + pb.notna().astype(float)) / 2.0, index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"pe={p}·pb={b}" for p, b in zip(pe, pb)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
