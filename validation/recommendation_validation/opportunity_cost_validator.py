"""validation.recommendation_validation.opportunity_cost_validator

Every HOLD must expose all 3 OC fields (Constitution Article 25).
"""
from __future__ import annotations


def validate_oc_enrichment(enrichments: list[dict]) -> tuple[bool, list[str]]:
    """Validate a list of OpportunityCostEnrichment dicts."""
    issues: list[str] = []
    required = ["hold_ticker", "oc_next_best_ticker", "oc_next_best_score",
                 "oc_expected_alpha_delta", "oc_reason_not_to_rotate",
                 "schema_fingerprint", "schema_version"]
    for i, e in enumerate(enrichments):
        for f in required:
            if f not in e:
                issues.append(f"enrichment[{i}] missing field: {f}")
        if e.get("schema_fingerprint") != "aegis.opportunity_cost.v1.20260727":
            issues.append(f"enrichment[{i}] wrong schema_fingerprint")
        if not e.get("oc_reason_not_to_rotate"):
            issues.append(f"enrichment[{i}] empty oc_reason_not_to_rotate")
    return (not issues), issues
