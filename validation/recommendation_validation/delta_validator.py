"""validation.recommendation_validation.delta_validator · Phase 3 invariants."""
from __future__ import annotations


def validate_deltas(deltas: list[dict]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for i, d in enumerate(deltas):
        for k in ("ticker", "current_action", "confidence_delta",
                   "technical_delta", "reason_for_change",
                   "ai_explanation_hint", "schema_fingerprint"):
            if k not in d: issues.append(f"delta[{i}] missing {k}")
        if d.get("schema_fingerprint") != "aegis.recommendation_delta.v1.20260727":
            issues.append(f"delta[{i}] wrong fingerprint")
        # if rank_delta present, current-prev consistency
        rd = d.get("rank_delta")
        pr, cr = d.get("previous_rank"), d.get("current_rank")
        if rd is not None and pr is not None and cr is not None:
            if rd != (pr - cr):
                issues.append(f"delta[{i}] rank_delta {rd} != prev {pr} - curr {cr}")
    return (not issues), issues
