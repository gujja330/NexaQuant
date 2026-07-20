"""Ensemble — combines multiple model predictions into a single scored view.

v0 (Sprint 2.7): equal-weight OR operator-supplied YAML weights.
v1 (Sprint 9+): WF-performance-weighted, regime-aware.

**No auto-promotion.** If an operator wants to change weights, they edit
configs/ensemble_weights.yaml. Weight changes are ledger-logged for audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class EnsembleWeights:
    """Per-model weight in [0, 1]. Weights are normalised to sum to 1."""
    weights: dict[str, float] = field(default_factory=dict)   # model_id -> weight
    strategy: str = "equal_weight"                             # "equal_weight" | "wf_weighted" | "manual"

    def normalize(self) -> dict[str, float]:
        s = sum(max(0.0, v) for v in self.weights.values())
        if s == 0:
            return {}
        return {k: max(0.0, v) / s for k, v in self.weights.items()}


@dataclass
class Ensemble:
    market:     str
    asof:       date
    strategy:   str
    weights:    dict = field(default_factory=dict)
    n_models:   int = 0
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes:      list[str] = field(default_factory=list)


def ensemble_predict(model_predictions: list, weights: EnsembleWeights | None = None,
                       market: str = "?", asof: date | None = None) -> Ensemble:
    """Combine a list of ModelPrediction into one aggregated scoreboard."""
    if not model_predictions:
        return Ensemble(market=market, asof=asof or date.today(),
                          strategy="empty", weights={}, n_models=0,
                          predictions=pd.DataFrame(),
                          notes=["no model predictions provided"])

    # Default weights: equal
    if weights is None or not weights.weights:
        weights = EnsembleWeights(
            weights={p.model_id: 1.0 for p in model_predictions},
            strategy="equal_weight",
        )
    w_norm = weights.normalize()

    # Aggregate per ticker
    all_scores: dict[str, list[tuple[str, float, float]]] = {}
    for p in model_predictions:
        for _, r in p.predictions.iterrows():
            t = str(r["ticker"])
            all_scores.setdefault(t, []).append(
                (p.model_id, float(r["score"]), float(r["confidence"])))

    rows = []
    for t, entries in all_scores.items():
        weighted_score = 0.0
        weighted_conf  = 0.0
        total_w = 0.0
        per_model_scores = {}
        for mid, s, c in entries:
            w = w_norm.get(mid, 0.0)
            weighted_score += w * s
            weighted_conf  += w * c
            total_w        += w
            per_model_scores[mid] = round(s, 4)
        if total_w == 0: total_w = 1.0
        rows.append({
            "ticker":            t,
            "ensemble_score":    round(weighted_score / total_w, 4),
            "ensemble_confidence": round(weighted_conf / total_w, 4),
            "n_models_scoring":  len(entries),
            "per_model_score":   per_model_scores,
        })

    df = pd.DataFrame(rows).sort_values("ensemble_score", ascending=False).reset_index(drop=True)
    return Ensemble(
        market=market, asof=asof or date.today(),
        strategy=weights.strategy, weights=w_norm, n_models=len(model_predictions),
        predictions=df,
        notes=[f"combined {len(model_predictions)} models across {len(df)} tickers"],
    )
