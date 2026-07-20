"""Trend Model — ADX + 52W distance + SMA alignment."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class TrendModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.trend.v1", model_type=ModelType.TREND, version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=["adx_14", "distance_from_52w_high_pct",
                                "price_above_sma50", "price_above_sma200"],
        business_rationale=("Persistent uptrends are the safest kind of bull; "
                             "strong ADX with price near 52W high signals conviction."),
        economic_intuition=("Trends form when structural demand outpaces supply; "
                             "confirmed trends persist longer than reversal patterns."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        adx  = df.get("adx_14", pd.Series([None] * len(df))).astype(float)
        d52h = df.get("distance_from_52w_high_pct", pd.Series([None] * len(df))).astype(float)
        s50  = df.get("price_above_sma50", pd.Series([None] * len(df))).astype(float)
        s200 = df.get("price_above_sma200", pd.Series([None] * len(df))).astype(float)

        # Positive score when ADX is strong AND price is near 52W high AND above key SMAs
        composite = (0.4 * rank_score(adx) + 0.3 * rank_score(-d52h.abs()) +
                       0.15 * s50.fillna(0) + 0.15 * s200.fillna(0))
        conf = pd.Series((adx.notna().astype(float) + s50.notna().astype(float)) / 2.0,
                          index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"adx={a}·dist_52wh={d}" for a, d in zip(adx, d52h)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
