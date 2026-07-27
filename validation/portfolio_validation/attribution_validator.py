"""validation.portfolio_validation.attribution_validator

Constitution Article 25 · sum-of-contributions must reconcile with realized return.
"""
from __future__ import annotations


def validate_portfolio_attribution(rep: dict) -> tuple[bool, list[str]]:
    """Validate serialized PortfolioAttribution dict. Returns (passed, issues)."""
    issues: list[str] = []
    required = ["engine", "version", "schema_version", "schema_fingerprint",
                 "market", "asof", "n_positions", "positions", "aggregate_contributions"]
    for f in required:
        if f not in rep:
            issues.append(f"missing top-level field: {f}")
    if issues:
        return False, issues
    if rep["schema_fingerprint"] != "aegis.portfolio_attribution.v1.20260727":
        issues.append("wrong schema_fingerprint")
    for i, p in enumerate(rep.get("positions", [])):
        realized = float(p.get("realized_return_pct", 0.0))
        contribs = p.get("contributions", {})
        total = sum(float(v) for v in contribs.values())
        if abs(total - realized) > 1e-3:
            issues.append(f"position[{i}] {p.get('ticker')} · contributions sum {total} != realized {realized}")
    return (not issues), issues
