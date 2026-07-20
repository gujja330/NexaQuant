"""Macro Model — market regime, rates, dollar, oil, VIX (market-level; broadcast tilt)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType,
)


class MacroModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.macro.v1", model_type=ModelType.MACRO, version="1.0.0",
        algorithm="weighted_rule_v1",
        feature_dependencies=["macro_10y", "macro_vix", "macro_wti_oil", "macro_dxy",
                                "mi_composite_score", "mi_regime"],
        business_rationale=("Macro backdrop conditions the *level* of equity returns "
                             "across the whole market. A hostile macro can override "
                             "individual company merit."),
        economic_intuition=("Rates + dollar + energy + volatility are the four master "
                             "levers of equity risk premium."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        # Macro model produces the SAME score for every ticker (market tilt)
        composite_val = 0.0
        conf_val = 0.0
        # Health composite from Market Intelligence directly
        if "mi_composite_score" in df.columns:
            mi = df["mi_composite_score"].dropna()
            if len(mi):
                # Map 0..100 to -1..+1
                composite_val = float((mi.iloc[0] - 50) / 50)
                conf_val = 0.8
        # VIX dampener
        if "macro_vix" in df.columns:
            vix_val = df["macro_vix"].dropna()
            if len(vix_val):
                v = float(vix_val.iloc[0])
                if v > 25: composite_val *= 0.6
                if v > 30: composite_val = min(composite_val, 0.0)

        composite = pd.Series(max(-1.0, min(1.0, composite_val)), index=df.index)
        conf = pd.Series(conf_val, index=df.index)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite,
            "confidence": conf,
            "evidence":   [f"mi_composite={df.get('mi_composite_score', pd.Series([None])).iloc[0] if len(df) else None}"] * len(df),
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
            notes=["market-level tilt broadcast to every ticker"],
        )
