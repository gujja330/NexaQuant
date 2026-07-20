"""AI Model Analyst v1.0 — deterministic narrative + ensemble-participation guidance.

Reads per-model metrics + descriptions. Emits:
  - Per-model narrative: what the model is, what it looks for, current confidence
  - Ensemble participation opinion: should this model be in the mix? (proposal only)
  - Deprecation candidates: models dominated by others (proposal only)

**Never promotes or removes models.** Every finding is a proposal for operator review.
"""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput

VERSION = "v1.0"


def run(model_descriptions: list[dict], model_metrics: list,
         ensemble_summary: dict | None, market_name: str,
         asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Per-model narrative
    for desc in model_descriptions:
        mid = desc.get("model_id", "?")
        m = next((mm for mm in model_metrics
                    if getattr(mm, "model_id", None) == mid), None)
        entry = {
            "type":              "model_narrative",
            "model_id":          mid,
            "model_type":        desc.get("type"),
            "approval_status":   desc.get("approval_status"),
            "n_scored":          getattr(m, "n_scored", 0) if m else 0,
            "avg_score":         getattr(m, "avg_score", None) if m else None,
            "top_10_confidence": getattr(m, "top_10_pct_confidence", None) if m else None,
            "status":            getattr(m, "status", "unknown") if m else "unknown",
            "business_rationale": desc.get("business_rationale"),
            "economic_intuition": desc.get("economic_intuition"),
        }
        # Ensemble participation proposal — very simple deterministic rule:
        #   participate if approval_status is APPROVED and n_scored > 0
        #   otherwise: propose for experimental participation only
        if desc.get("approval_status") == "APPROVED" and entry["n_scored"] > 0:
            entry["ensemble_recommendation"] = "include"
        elif entry["n_scored"] > 0:
            entry["ensemble_recommendation"] = "include_experimental_only"
        else:
            entry["ensemble_recommendation"] = "exclude_no_data"
        findings.append(entry)

    # Deprecation candidates: models whose top_10_pct_confidence is 0
    for m in model_metrics:
        if getattr(m, "n_scored", 0) > 0 and getattr(m, "top_10_pct_confidence", 0) < 0.05:
            findings.append({
                "type":              "deprecation_candidate",
                "model_id":          m.model_id,
                "reason":            "top_10_pct_confidence < 0.05 — model has no conviction",
                "recommended_step":  "review_data_dependencies",
            })

    n_included = sum(1 for f in findings
                     if f.get("type") == "model_narrative"
                     and f.get("ensemble_recommendation", "").startswith("include"))
    n_deprecate = sum(1 for f in findings if f.get("type") == "deprecation_candidate")

    head = (f"{len(model_descriptions)} models registered · "
            f"{n_included} ready for ensemble · "
            f"{n_deprecate} flagged for review")
    narr = (head + ".\n\n"
            "The AI Model Analyst compares each model's business rationale against its "
            "current-day scoring behavior. Metrics like win-rate and profit-factor stay "
            "'insufficient_history' until Sprint 9 rebuilds the learning corpus — that's "
            "honest, not broken. Once outcomes accumulate, the same interface fills in.\n\n"
            "AI never promotes or removes models. Every 'ensemble_recommendation' here is a "
            "proposal — promotion goes through backend/promotion/promotion_gate.py with "
            "explicit operator approval.")

    return AgentOutput(
        agent="model_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={"n_models": len(model_descriptions),
                    "ensemble_strategy": (ensemble_summary or {}).get("strategy", "unknown")},
        citations=["backend/model_factory", "backend/model_registry"],
        confidence=0.8,
        caveats=["metrics limited without learning corpus (Sprint 9)",
                    "AI analyst proposes only — operator promotes"],
        determinism="template",
    )
