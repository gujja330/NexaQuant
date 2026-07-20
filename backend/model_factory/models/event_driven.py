"""Event-Driven Model — earnings + corp actions + insider."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.model_factory.model_base import (
    BaseModel, ModelMetadata, ModelPrediction, ModelType, rank_score,
)


class EventDrivenModel(BaseModel):
    METADATA = ModelMetadata(
        model_id="aegis.event_driven.v1", model_type=ModelType.EVENT_DRIVEN,
        version="1.0.0", algorithm="weighted_rule_v1",
        feature_dependencies=[
            "earn_days_to_next", "earn_last_surprise_pct",
            "insider_net_90d", "ca_days_since_last_dividend",
        ],
        business_rationale=("Discrete events (earnings, insider trades, dividends) "
                             "create predictable pockets of alpha via PEAD, insider signal, "
                             "and dividend anchor."),
        economic_intuition=("Anchoring bias + slow analyst updates cause gradual price "
                             "adjustment for weeks post-event."),
        approval_status="EXPERIMENTAL",
    )

    def train(self, features, target, cutoff): pass

    def predict(self, features: pd.DataFrame, cutoff: date) -> ModelPrediction:
        df = features.copy()
        surp = df.get("earn_last_surprise_pct", pd.Series([None] * len(df))).astype(float)
        days = df.get("earn_days_to_next", pd.Series([None] * len(df))).astype(float)
        ins  = df.get("insider_net_90d", pd.Series([None] * len(df))).astype(float)

        # PEAD-style: recent positive surprise + 1-90 days until next report
        pead_mult = ((days.notna() & (days > 0) & (days < 90)).astype(float))
        pead_signal = rank_score(surp) * pead_mult

        insider_signal = rank_score(ins)   # net positive = bullish
        composite = 0.6 * pead_signal + 0.4 * insider_signal

        conf = pd.Series((surp.notna().astype(float) + ins.notna().astype(float)) / 2.0,
                          index=df.index).fillna(0.0)
        preds = pd.DataFrame({
            "ticker":     df["ticker"] if "ticker" in df.columns else df.index,
            "score":      composite.clip(-1, 1).fillna(0.0),
            "confidence": conf,
            "evidence":   [f"surprise={s}·days_to_next={d}·insider_net={i}"
                              for s, d, i in zip(surp, days, ins)],
        }).reset_index(drop=True)
        return ModelPrediction(
            model_id=self.metadata.model_id,
            market=str(df["market"].iloc[0]) if "market" in df.columns else "?",
            asof=cutoff, predictions=preds, n_scored=int(len(preds)),
        )
