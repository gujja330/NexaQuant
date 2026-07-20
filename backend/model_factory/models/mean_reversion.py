"""Mean Reversion Model — oversold conditions with quality filter."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class MeanReversionModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.mean_reversion.v1", model_type=ModelType.MEAN_REVERSION,
        version="1.0.0", algorithm="weighted_rule_v1",
        feature_dependencies=["rsi_14", "max_drawdown_60d_pct",
                                "distance_from_52w_low_pct", "fund_quality_score"],
        business_rationale=("Short-term overreaction produces exploitable snapbacks in "
                             "high-quality names; low-quality names deserve their drawdown."),
        economic_intuition=("Panic selling detaches price from fundamentals; the gap "
                             "closes over 1-4 weeks in fundamentally intact companies."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        rsi = df.get("rsi_14", pd.Series([None] * len(df))).astype(float)
        dd  = df.get("max_drawdown_60d_pct", pd.Series([None] * len(df))).astype(float)
        d52 = df.get("distance_from_52w_low_pct", pd.Series([None] * len(df))).astype(float)
        qs  = df.get("fund_quality_score", pd.Series([None] * len(df))).astype(float)

        # Signal is STRONGER for lower RSI + deeper drawdown, provided quality holds
        oversold  = (30 - rsi).clip(lower=0)          # 0 unless RSI<30
        deep_dd   = (-dd).clip(lower=0)               # positive drawdown magnitude
        near_low  = (10 - d52.clip(lower=0)).clip(lower=0)   # within 10% of 52w low
        raw = rank_score(oversold) + rank_score(deep_dd) + rank_score(near_low)
        quality_gate = rank_score(qs)
        composite = 0.6 * raw + 0.4 * quality_gate

        conf = pd.Series(((rsi.notna() | dd.notna() | d52.notna()).astype(float)
                            + qs.notna().astype(float)) / 2.0, index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"rsi={r}·dd={d}·d_from_low={dl}"
                              for r, d, dl in zip(rsi, dd, d52)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
