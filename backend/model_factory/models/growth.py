"""Growth Model — earnings growth + ROE."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class GrowthModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.growth.v1", model_type=ModelType.GROWTH, version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=["fund_earnings_growth", "fund_roe"],
        business_rationale=("Compounding earnings expansion drives multi-year returns; "
                             "growth premium is durable when quality holds."),
        economic_intuition=("Companies re-investing earnings at high incremental returns "
                             "compound intrinsic value faster than the market prices in."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        eg = df.get("fund_earnings_growth", pd.Series([None] * len(df))).astype(float)
        roe = df.get("fund_roe", pd.Series([None] * len(df))).astype(float)
        composite = 0.6 * rank_score(eg) + 0.4 * rank_score(roe)
        conf = pd.Series((eg.notna().astype(float) + roe.notna().astype(float)) / 2.0,
                          index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"eps_growth={g}·roe={r}" for g, r in zip(eg, roe)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
