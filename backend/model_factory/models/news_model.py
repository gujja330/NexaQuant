"""News Model — sentiment + polarity + headline volume."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class NewsModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.news.v1", model_type=ModelType.NEWS, version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=["news_sentiment", "news_polarity_ratio",
                                "news_n_headlines", "news_n_positive", "news_n_negative"],
        business_rationale=("News sentiment drives short-term price action before "
                             "analysts update their models."),
        economic_intuition=("Attention + narrative shape near-term flows; positive "
                             "news attracts retail + momentum traders, negative repels them."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        s = df.get("news_sentiment", pd.Series([None] * len(df))).astype(float)
        pol = df.get("news_polarity_ratio", pd.Series([None] * len(df))).astype(float)
        n = df.get("news_n_headlines", pd.Series([None] * len(df))).astype(float)

        # Sentiment matters more when supported by volume
        volume_scale = (n.clip(0, 20) / 20.0).fillna(0.5)
        composite = 0.6 * rank_score(s) + 0.3 * rank_score(pol) + 0.1 * rank_score(volume_scale)
        conf = pd.Series((s.notna().astype(float) + n.notna().astype(float)) / 2.0,
                          index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"sent={ss}·headlines={int(nn) if pd.notna(nn) else '-'}"
                              for ss, nn in zip(s, n)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
