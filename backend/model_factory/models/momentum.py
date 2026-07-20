"""Momentum Model.

Signal: cross-sectional momentum score from returns + MA alignment.
Rationale: prices in motion tend to stay in motion for horizons of weeks-to-months
           (Jegadeesh & Titman 1993; documented anomaly across decades and markets).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class MomentumModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.momentum.v1",
        model_type=ModelType.MOMENTUM,
        version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=[
            "return_5d_pct", "return_20d_pct", "return_60d_pct",
            "price_above_sma20", "price_above_sma50", "price_above_sma200",
            "rsi_14",
        ],
        business_rationale=("Cross-sectional momentum has one of the most durable "
                             "risk premiums in equities — winners keep winning "
                             "over 3-12 month horizons."),
        economic_intuition=("Slow information diffusion + behavioral anchoring "
                             "cause under-reaction; momentum rides that under-reaction."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff):
        # Rule-based — no training needed; state stays empty.
        pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        weights = {
            "return_5d_pct":       0.15,
            "return_20d_pct":      0.30,
            "return_60d_pct":      0.25,
            "price_above_sma20":   0.10,
            "price_above_sma50":   0.10,
            "price_above_sma200":  0.10,
        }
        # RSI penalty: overbought stocks (>75) get their score capped, oversold (<25) also skepticised
        composite = pd.Series(0.0, index=df.index)
        n_available = 0
        for col, w in weights.items():
            if col not in df.columns: continue
            s = df[col].fillna(0.0)
            composite = composite + w * rank_score(s)
            n_available += 1

        # RSI dampener — capped scores in overbought regime
        if "rsi_14" in df.columns:
            rsi_mult = ((df["rsi_14"] < 75).astype(float) * 1.0) + \
                        ((df["rsi_14"] >= 75).astype(float) * 0.6)
            composite = composite * rsi_mult.fillna(1.0)

        confidence = pd.Series(min(1.0, n_available / len(weights)), index=df.index)

        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1),
            "confidence": confidence,
            "evidence":   [
                f"return_20d={r20 if pd.notna(r20) else '-'}·"
                f"return_60d={r60 if pd.notna(r60) else '-'}·"
                f"above_sma200={a200 if pd.notna(a200) else '-'}"
                for r20, r60, a200 in zip(
                    df.get("return_20d_pct", pd.Series([None] * len(df))),
                    df.get("return_60d_pct", pd.Series([None] * len(df))),
                    df.get("price_above_sma200", pd.Series([None] * len(df))),
                )
            ],
        }).reset_index(drop=True)

        return ModelPrediction(
            model_id=self.metadata.model_id, market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
            notes=[f"{n_available}/{len(weights)} weighted features available"],
        )
