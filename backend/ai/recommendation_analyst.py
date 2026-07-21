"""AI Recommendation Analyst v1.0 — reviews the Recommendation batch.

Emits:
  - Sanity checks: are BUY/SELL splits sensible for the regime?
  - Disagreement audit: how many calls collapsed to HOLD via conflict?
  - Top-conviction highlights: highest calibrated_confidence STRONG_BUY / STRONG_SELL
  - Deprecation-candidate calls: recommendations with very low evidence coverage

**Never promotes recommendations**. Everything here is descriptive.
"""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput

VERSION = "v1.0"


def run(batch, regime: str, market_name: str,
         asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Batch composition
    n = batch.n_tickers
    dist = {
        "STRONG_BUY":  batch.n_strong_buy,
        "BUY":         batch.n_buy,
        "HOLD":        batch.n_hold,
        "SELL":        batch.n_sell,
        "STRONG_SELL": batch.n_strong_sell,
    }
    findings.append({
        "type":         "batch_composition",
        "n_tickers":    n,
        "distribution": dist,
        "regime":       regime,
        "n_disagreement_collapsed_to_hold": batch.n_disagreement,
    })

    # Regime sanity
    if regime == "bull" and (dist["STRONG_SELL"] + dist["SELL"]) > (dist["STRONG_BUY"] + dist["BUY"]) * 2:
        findings.append({
            "type": "regime_anomaly",
            "note": "bull regime yet SELL calls dominate — check inputs or lower confidence thresholds",
        })
    if regime in ("bear", "stress") and (dist["STRONG_BUY"] + dist["BUY"]) > (dist["STRONG_SELL"] + dist["SELL"]) * 2:
        findings.append({
            "type": "regime_anomaly",
            "note": f"{regime} regime yet BUY calls dominate — verify model_metrics + calibration",
        })

    # Top conviction
    strong_buys = [r for r in batch.recommendations if r.action.value == "STRONG_BUY"]
    strong_buys.sort(key=lambda r: r.regime_adjusted_confidence, reverse=True)
    for r in strong_buys[:5]:
        findings.append({
            "type": "top_conviction_buy",
            "ticker":      r.ticker,
            "score":       r.ensemble_score,
            "confidence":  r.regime_adjusted_confidence,
            "agreement":   r.model_agreement,
            "top_models":  [m["model_id"] for m in (r.top_models or [])],
        })

    strong_sells = [r for r in batch.recommendations if r.action.value == "STRONG_SELL"]
    strong_sells.sort(key=lambda r: r.regime_adjusted_confidence, reverse=True)
    for r in strong_sells[:5]:
        findings.append({
            "type":        "top_conviction_sell",
            "ticker":      r.ticker,
            "score":       r.ensemble_score,
            "confidence":  r.regime_adjusted_confidence,
            "agreement":   r.model_agreement,
            "top_models":  [m["model_id"] for m in (r.top_models or [])],
        })

    # Low-coverage warnings
    low_cov = [r for r in batch.recommendations
               if r.calibrated_confidence < 0.30 and r.action.value != "HOLD"]
    for r in low_cov[:5]:
        findings.append({
            "type":              "low_evidence_warning",
            "ticker":            r.ticker,
            "action":            r.action.value,
            "calibrated_conf":   r.calibrated_confidence,
            "n_models_scoring":  r.n_models_scoring,
            "note":              "consider tightening thresholds or waiting for more data",
        })

    head = (f"{n} recommendations · "
             f"{dist['STRONG_BUY']} STRONG_BUY · {dist['BUY']} BUY · "
             f"{dist['HOLD']} HOLD · {dist['SELL']} SELL · {dist['STRONG_SELL']} STRONG_SELL · "
             f"regime={regime}")
    narr = (head + ".\n\n"
            "This is a sanity + conviction audit of the current Recommendation batch. "
            "It flags regime anomalies, highlights the highest-confidence conviction calls, "
            "and warns on low-evidence recommendations. "
            "It does NOT approve or promote any call — every recommendation is EXPERIMENTAL "
            "until promoted via backend.promotion.promotion_gate.approve_model with WF evidence.")

    return AgentOutput(
        agent="recommendation_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={"n_tickers": n, "distribution": dist, "regime": regime},
        citations=["backend/recommendation/engine.py"],
        confidence=0.85,
        caveats=[
            "descriptive audit only — never promotes",
            "metrics are ex-ante; live-forward outcomes populate via Sprint 6 Learning Engine",
        ],
        determinism="template",
    )
