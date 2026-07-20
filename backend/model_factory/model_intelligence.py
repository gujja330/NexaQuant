"""Model Intelligence — metrics harness for each registered model.

Sprint 2.7 computes the metrics FROM available data. When the learning
corpus is empty (Stage 0.5 Finding 1), most metrics return
`insufficient_history` — that's honest, not broken. Sprint 9's Learning
Engine populates the outcome labels these need.

Metrics per model:
  win_rate                 (needs outcomes)
  precision                (needs outcomes)
  recall                   (needs outcomes)
  sharpe                   (needs return series)
  sortino                  (needs return series)
  max_drawdown             (needs equity curve)
  profit_factor            (needs outcomes)
  stability                (needs multi-window WF)
  regime_performance       (needs regime-labeled outcomes)
  walk_forward_performance (needs WF runner — Sprint 10)
  turnover                 (from prediction diffs day-over-day)
  avg_holding_period       (from lifecycle ledger)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd


@dataclass
class ModelMetrics:
    model_id:     str
    market:       str
    asof:         date
    n_scored:     int
    avg_score:    float
    top_10_pct_confidence: float                 # avg confidence of the top-10% scores
    win_rate:                 float | None = None
    precision:                float | None = None
    recall:                   float | None = None
    sharpe:                   float | None = None
    sortino:                  float | None = None
    max_drawdown:             float | None = None
    profit_factor:            float | None = None
    stability:                float | None = None
    regime_performance:       dict = field(default_factory=dict)
    walk_forward_performance: dict = field(default_factory=dict)
    turnover:                 float | None = None
    avg_holding_period_days:  float | None = None
    status:                   str = "insufficient_history"


def evaluate_model(prediction, learning_corpus_path: Path | None = None) -> ModelMetrics:
    """Given a ModelPrediction, compute what metrics we can.

    If learning_corpus_path is provided and points to a valid parquet, we can
    fill more metrics; otherwise most fields stay None.
    """
    p = prediction
    preds = p.predictions
    if preds is None or preds.empty:
        return ModelMetrics(
            model_id=p.model_id, market=p.market, asof=p.asof,
            n_scored=0, avg_score=0.0, top_10_pct_confidence=0.0,
            status="empty",
        )

    scores = preds["score"].astype(float)
    conf   = preds["confidence"].astype(float)
    avg_score = round(float(scores.mean()), 4)
    n_top = max(1, int(len(scores) * 0.1))
    top_idx = scores.rank(ascending=False, method="first").astype(int).le(n_top)
    top10_conf = round(float(conf[top_idx].mean()) if top_idx.any() else 0.0, 4)

    m = ModelMetrics(
        model_id=p.model_id, market=p.market, asof=p.asof,
        n_scored=int(p.n_scored), avg_score=avg_score,
        top_10_pct_confidence=top10_conf,
        status="insufficient_history",
    )

    # ── If learning corpus is present, we can compute win_rate etc.
    if learning_corpus_path and Path(learning_corpus_path).exists():
        try:
            corpus = pd.read_parquet(learning_corpus_path)
            if "is_winner" in corpus.columns and "ticker" in corpus.columns and len(corpus) > 20:
                # Rough proxy: which of THIS model's top-scored tickers are historical winners?
                top_tickers = set(preds.loc[top_idx, "ticker"].astype(str))
                subset = corpus[corpus["ticker"].astype(str).isin(top_tickers)]
                if len(subset) >= 10:
                    m.win_rate = round(float(subset["is_winner"].mean()), 4)
                    if "return_pct" in subset.columns:
                        winners = subset[subset["is_winner"] == True]["return_pct"] if "is_winner" in subset else pd.Series([])
                        losers  = subset[subset["is_winner"] == False]["return_pct"] if "is_winner" in subset else pd.Series([])
                        if len(winners) > 0 and len(losers) > 0 and losers.sum() != 0:
                            m.profit_factor = round(float(winners.sum() / abs(losers.sum())), 3)
                    m.status = "computed_from_learning_corpus"
        except Exception:
            pass

    return m
