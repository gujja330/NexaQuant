"""validation.recommendation_validation.dynamic_holding_validator · Phase 4 invariants."""
from __future__ import annotations


def validate_holding_decision(d: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    required = ("ticker", "holding_days", "base_days", "regime_multiplier",
                 "confidence_factor", "upside_factor", "sector_factor",
                 "rotation_factor", "risk_factor", "volatility_factor",
                 "liquidity_factor", "portfolio_overlap_factor",
                 "opportunity_cost_factor", "benchmark_alpha_factor",
                 "reason", "schema_fingerprint")
    for k in required:
        if k not in d: issues.append(f"missing {k}")
    if d.get("schema_fingerprint") != "aegis.dynamic_holding.v1.20260727":
        issues.append("wrong fingerprint")
    hd = d.get("holding_days", 0)
    if not (3 <= hd <= 180):
        issues.append(f"holding_days out of [3,180]: {hd}")
    return (not issues), issues
