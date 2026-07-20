"""Quality Model — ROE + margins + inverse D/E + composite quality score."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class QualityModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.quality.v1", model_type=ModelType.QUALITY, version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=["fund_roe", "fund_profit_margin", "fund_debt_to_equity",
                                "fund_quality_score"],
        business_rationale=("High-quality companies compound; low-quality ones erode capital. "
                             "Quality is the single most stable factor across regimes."),
        economic_intuition=("Structural moats (brand, network, IP, cost advantage) produce "
                             "persistent excess returns on capital that survive competitive erosion."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        roe   = df.get("fund_roe", pd.Series([None] * len(df))).astype(float)
        mgn   = df.get("fund_profit_margin", pd.Series([None] * len(df))).astype(float)
        de    = df.get("fund_debt_to_equity", pd.Series([None] * len(df))).astype(float)
        qsc   = df.get("fund_quality_score", pd.Series([None] * len(df))).astype(float)

        inv_de = -1.0 * de     # lower D/E is better
        composite = (0.30 * rank_score(roe) + 0.20 * rank_score(mgn) +
                       0.20 * rank_score(inv_de) + 0.30 * rank_score(qsc))
        conf = pd.Series((roe.notna().astype(float) + mgn.notna().astype(float) +
                             de.notna().astype(float) + qsc.notna().astype(float)) / 4.0,
                          index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"roe={r}·mgn={m}·d/e={d}·quality={q}"
                              for r, m, d, q in zip(roe, mgn, de, qsc)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
