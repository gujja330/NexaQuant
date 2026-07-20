"""Feature Governance Engine — validates that every registered feature
carries the required metadata (Sprint 2.6).

The two anchors the user set today:
  business_rationale — WHY this feature should predict returns or risk
  economic_intuition — what market behavior it represents

Missing rationale/intuition = documentation debt, not a hard error.
Governance surfaces the gap; operator prioritises the fill.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from backend.feature_store.feature_registry import (
    FEATURE_REGISTRY, Feature, FeatureStatus, FeatureCategory,
)


@dataclass
class GovernanceResult:
    n_features:              int
    n_active:                int
    n_experimental:          int
    n_deprecated:            int
    missing_rationale:       list[str] = field(default_factory=list)   # feature names
    missing_intuition:       list[str] = field(default_factory=list)
    missing_formula:         list[str] = field(default_factory=list)
    missing_owner:           list[str] = field(default_factory=list)
    coverage_rationale_pct:  float = 0.0
    coverage_intuition_pct:  float = 0.0
    coverage_formula_pct:    float = 0.0
    verdict:                 str = "PASS"     # PASS | WARNING | FAIL


IDENTITY_EXEMPT = {"market", "ticker", "asof", "sector", "currency"}


def validate_governance(as_of: date | None = None) -> GovernanceResult:
    """Audit the registry for governance completeness."""
    r = GovernanceResult(
        n_features     = len(FEATURE_REGISTRY),
        n_active       = sum(1 for f in FEATURE_REGISTRY if f.status == FeatureStatus.ACTIVE),
        n_experimental = sum(1 for f in FEATURE_REGISTRY if f.status == FeatureStatus.EXPERIMENTAL),
        n_deprecated   = sum(1 for f in FEATURE_REGISTRY if f.status == FeatureStatus.DEPRECATED),
    )

    n_checkable = 0
    n_with_rat = n_with_int = n_with_for = 0
    for f in FEATURE_REGISTRY:
        if f.name in IDENTITY_EXEMPT: continue   # identity cols don't need rationale
        n_checkable += 1
        if f.business_rationale.strip():
            n_with_rat += 1
        else:
            r.missing_rationale.append(f.name)
        if f.economic_intuition.strip():
            n_with_int += 1
        else:
            r.missing_intuition.append(f.name)
        if f.formula.strip():
            n_with_for += 1
        else:
            r.missing_formula.append(f.name)
        if not f.owner.strip() or f.owner == "aegis-core":
            r.missing_owner.append(f.name)      # placeholder default counts as missing

    if n_checkable > 0:
        r.coverage_rationale_pct = round(n_with_rat / n_checkable * 100, 2)
        r.coverage_intuition_pct = round(n_with_int / n_checkable * 100, 2)
        r.coverage_formula_pct   = round(n_with_for / n_checkable * 100, 2)

    # Verdict — documentation debt is WARNING, not FAIL. FAIL only if
    # registry itself is broken (empty).
    if r.n_features == 0:
        r.verdict = "FAIL"
    elif r.coverage_rationale_pct < 20 or r.coverage_intuition_pct < 20:
        r.verdict = "WARNING"
    else:
        r.verdict = "PASS"
    return r
