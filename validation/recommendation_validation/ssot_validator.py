"""validation.recommendation_validation.ssot_validator

Constitution Article 25 · Phase 1 SSoT invariants.
"""
from __future__ import annotations


def validate_ssot(payload: dict) -> tuple[bool, list[str]]:
    """Validate the SSoT-published recommendations.json payload."""
    issues: list[str] = []
    required = ["engine", "version", "schema_version", "schema_fingerprint",
                 "market", "asof", "run_utc", "source", "n", "recommendations"]
    for f in required:
        if f not in payload:
            issues.append(f"missing top-level: {f}")
    if issues: return False, issues
    if payload["engine"] != "aegis.recommendation.ssot.v1":
        issues.append(f"wrong engine: {payload['engine']}")
    if payload["schema_fingerprint"] != "aegis.recommendation_ssot.v1.20260727":
        issues.append("wrong schema_fingerprint")
    if payload["n"] != len(payload["recommendations"]):
        issues.append(f"n mismatch: {payload['n']} != {len(payload['recommendations'])}")
    for i, r in enumerate(payload["recommendations"]):
        for k in ("ticker", "recommendation", "action", "composite_decision_score", "confidence", "rank"):
            if k not in r: issues.append(f"rec[{i}] missing {k}")
        if r.get("recommendation") not in ("STRONG BUY","BUY","ADD","HOLD","TRIM","SELL","STRONG SELL","EXIT","ROTATED"):
            issues.append(f"rec[{i}] invalid recommendation: {r.get('recommendation')}")
        if not (0.0 <= r.get("composite_decision_score", -1) <= 100.0):
            issues.append(f"rec[{i}] score out of [0,100]: {r.get('composite_decision_score')}")
        if not (0.0 <= r.get("confidence", -1) <= 1.0):
            issues.append(f"rec[{i}] confidence out of [0,1]: {r.get('confidence')}")
    return (not issues), issues
