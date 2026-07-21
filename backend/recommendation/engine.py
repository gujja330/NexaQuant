"""RecommendationEngine — composes conflict + calibration + regime + classify + explain.

Reads ensemble.json + feature snapshot + market_intelligence_summary.json + optional
model_metrics.json → emits a RecommendationBatch. Deterministic, walk-forward safe.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from backend.recommendation.types        import (
    Action, Recommendation, RecommendationBatch,
)
from backend.recommendation.conflict     import resolve_conflict
from backend.recommendation.calibration  import calibrate_confidence, CalibrationInputs
from backend.recommendation.regime_adjust import apply_regime_adjustment
from backend.recommendation.classifier   import classify
from backend.recommendation.explainer    import explain


# Identity columns skipped when computing evidence coverage
_IDENTITY = {"market", "ticker", "asof", "sector", "currency"}


def _evidence_coverage(row: dict, selected: list[str]) -> float:
    """Fraction of selected features non-null on this row (0..1)."""
    if not selected: return 0.5
    non_null = 0
    for f in selected:
        if f in _IDENTITY: continue
        v = row.get(f)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            non_null += 1
    denom = max(1, len([f for f in selected if f not in _IDENTITY]))
    return round(non_null / denom, 4)


class RecommendationEngine:
    ENGINE_ID = "aegis.recommendation.v3"
    ENGINE_VERSION = "1.0.0"

    def __init__(self, repo_root: Path, market: str,
                    regime: str = "unknown",
                    schema_fingerprint: str = "",
                    feature_set_version: str = "",
                    model_stamp: dict | None = None):
        self.repo_root = Path(repo_root)
        self.market = market
        self.regime = regime
        self.schema_fingerprint = schema_fingerprint
        self.feature_set_version = feature_set_version
        self.model_stamp = dict(model_stamp) if model_stamp else {}

    def run(self, ensemble_top_rows: list[dict],
              features_df: pd.DataFrame,
              selected_features: list[str],
              asof: date | None = None) -> RecommendationBatch:
        """Convert ensemble output into per-ticker recommendations.

        ensemble_top_rows: list of {ticker, ensemble_score, ensemble_confidence,
                                     per_model_score: dict, n_models_scoring: int}
        features_df:       Feature Store snapshot restricted to selected features
        selected_features: list of selected feature names (for evidence coverage)
        """
        asof = asof or date.today()
        batch = RecommendationBatch(
            engine=self.ENGINE_ID, version=self.ENGINE_VERSION,
            market=self.market, asof=asof, n_tickers=0,
        )

        # Index features by ticker for fast lookup
        feats = features_df.set_index("ticker") if "ticker" in features_df.columns else features_df
        conflicts_ledger: list[dict] = []

        for row in ensemble_top_rows:
            ticker = str(row["ticker"])
            score  = float(row["ensemble_score"])
            raw_c  = float(row.get("ensemble_confidence", 0.0))
            per_m  = dict(row.get("per_model_score", {}) or {})

            # 1) Conflict resolver
            cr = resolve_conflict(per_m)

            # 2) Evidence coverage (from feature row)
            feature_row = feats.loc[ticker].to_dict() if ticker in feats.index else {}
            cov = _evidence_coverage(feature_row, selected_features)

            # 3) Calibrate
            cal = calibrate_confidence(CalibrationInputs(
                raw_confidence=raw_c, model_agreement=cr.model_agreement,
                evidence_coverage=cov, historical_precision=None,
            ))

            # 4) Regime adjustment
            reg_c, hold_days = apply_regime_adjustment(self.regime, score, cal)

            # 5) Classify
            action = classify(score, reg_c, cr.disagreement_flag)

            # 6) Explain
            expl = explain(feature_row, per_m, action, score, hold_days)

            # 7) Top-3 contributing models by |score|
            top_models_sorted = sorted(per_m.items(), key=lambda kv: abs(kv[1] or 0), reverse=True)[:3]
            top_models = [{"model_id": mid, "score": round(float(s), 4)}
                            for mid, s in top_models_sorted if s is not None]

            # 8) Top features present in the row (deterministic: sort by identifier)
            top_feats = [f for f in sorted(selected_features)
                          if f in feature_row
                          and feature_row.get(f) is not None
                          and not (isinstance(feature_row.get(f), float) and pd.isna(feature_row.get(f)))][:8]

            rec = Recommendation(
                market=self.market, ticker=ticker, asof=asof,
                action=action,
                ensemble_score=round(score, 4),
                raw_confidence=round(raw_c, 4),
                calibrated_confidence=cal,
                regime_adjusted_confidence=reg_c,
                model_agreement=cr.model_agreement,
                disagreement_flag=cr.disagreement_flag,
                n_models_scoring=cr.n_models_scoring,
                top_models=top_models,
                top_features=top_feats,
                bull_case=expl["bull_case"],
                bear_case=expl["bear_case"],
                key_risks=expl["key_risks"],
                suggested_holding_period_days=hold_days,
                entry_zone=expl["entry_zone"],
                exit_conditions=expl["exit_conditions"],
                model_stamp=self.model_stamp,
                feature_set_version=self.feature_set_version,
                schema_fingerprint=self.schema_fingerprint,
            )
            batch.recommendations.append(rec)

            if cr.disagreement_flag:
                conflicts_ledger.append({
                    "ticker": ticker,
                    "ensemble_score": round(score, 4),
                    "n_models_scoring": cr.n_models_scoring,
                    "n_positive": cr.n_positive,
                    "n_negative": cr.n_negative,
                    "model_agreement": cr.model_agreement,
                    "severity": cr.disagreement_severity,
                    "collapsed_to": action.value,
                })

        # Roll-ups
        batch.n_tickers = len(batch.recommendations)
        for r in batch.recommendations:
            if   r.action == Action.STRONG_BUY:  batch.n_strong_buy  += 1
            elif r.action == Action.BUY:         batch.n_buy         += 1
            elif r.action == Action.SELL:        batch.n_sell        += 1
            elif r.action == Action.STRONG_SELL: batch.n_strong_sell += 1
            else:                                 batch.n_hold        += 1
            if r.disagreement_flag:               batch.n_disagreement += 1

        batch.conflicts = conflicts_ledger
        batch.notes.append(f"engine={self.ENGINE_ID} v{self.ENGINE_VERSION} regime={self.regime}")
        return batch
