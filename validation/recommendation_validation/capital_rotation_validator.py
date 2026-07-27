"""validation.recommendation_validation.capital_rotation_validator

Constitution Article 25 · 27 · 28.
"""
from __future__ import annotations

from typing import Any


def validate_rotation_plan(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a serialized RotationPlan. Returns (passed, issues)."""
    issues: list[str] = []
    required_top = ["engine", "version", "schema_version", "schema_fingerprint",
                     "market", "asof", "macro_regime", "macro_gate",
                     "n_positions", "decisions"]
    for f in required_top:
        if f not in plan:
            issues.append(f"missing top-level field: {f}")
    if issues:
        return False, issues
    if plan["engine"] != "aegis.capital_rotation.v1":
        issues.append(f"wrong engine id: {plan['engine']}")
    if plan["schema_fingerprint"] != "aegis.capital_rotation.v1.20260727":
        issues.append(f"schema_fingerprint mismatch: {plan['schema_fingerprint']}")
    if not (0.0 <= plan["macro_gate"] <= 1.0):
        issues.append(f"macro_gate out of [0,1]: {plan['macro_gate']}")
    for i, d in enumerate(plan.get("decisions", [])):
        if d.get("action") not in ("KEEP", "ADD", "TRIM", "EXIT", "ROTATE"):
            issues.append(f"decision[{i}] invalid action: {d.get('action')}")
        ks = d.get("keep_score")
        if ks is not None and not (-1.0 <= ks <= 1.0):
            issues.append(f"decision[{i}] keep_score out of [-1,1]: {ks}")
        if d.get("action") == "ROTATE" and not d.get("candidate_ticker"):
            issues.append(f"decision[{i}] action=ROTATE but no candidate_ticker")
    return (not issues), issues
