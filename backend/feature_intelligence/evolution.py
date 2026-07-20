"""Feature Evolution — candidate feature pipeline (Sprint 2.6).

New features enter the system as **candidates**. They pass through:

  propose_candidate()    — a CandidateFeature record is created (Experimental status)
     ↓
  evaluate_candidate()   — runs quality + importance + drift on the candidate;
                           returns a report. Does NOT promote.
     ↓
  promotion_gate.approve() — operator explicitly promotes (Sprint 2.6 policy).

**AI never promotes.** AI Research Agent can propose_candidate() but promotion
is always an operator action. See `backend/promotion/promotion_gate.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from backend.feature_store.feature_registry import (
    FEATURE_REGISTRY, Feature, FeatureCategory, FeatureStatus,
)


@dataclass
class CandidateFeature:
    name:              str
    category:          FeatureCategory
    formula:           str
    business_rationale: str
    economic_intuition: str
    proposed_by:       str        # "human:surya" | "ai:research_agent" | ...
    proposed_on:       str        # ISO date
    dependencies:      tuple = ()
    notes:             str = ""


@dataclass
class CandidateEvaluation:
    candidate:         CandidateFeature
    passed_backtest:   bool = False       # placeholder — Sprint 9 fills this via WF
    passed_walk_forward: bool = False
    statistical_significance: float | None = None
    stability_across_regimes: float | None = None
    quality_ok:        bool = False
    importance_score:  float | None = None
    verdict:           str = "PENDING"    # PENDING | ACCEPT | REJECT
    reasons:           list[str] = field(default_factory=list)


def propose_candidate(name: str, category: FeatureCategory, formula: str,
                        business_rationale: str, economic_intuition: str,
                        proposed_by: str,
                        proposed_on: date | None = None,
                        dependencies: tuple = (),
                        notes: str = "") -> CandidateFeature:
    """Create a candidate record. Sprint 2.6 registers it but does NOT add it
    to the FEATURE_REGISTRY — promotion happens through the promotion_gate."""
    return CandidateFeature(
        name=name, category=category, formula=formula,
        business_rationale=business_rationale, economic_intuition=economic_intuition,
        proposed_by=proposed_by,
        proposed_on=(proposed_on or date.today()).isoformat(),
        dependencies=tuple(dependencies), notes=notes,
    )


def evaluate_candidate(candidate: CandidateFeature,
                         computed_values: pd.Series | None = None,
                         target: pd.Series | None = None) -> CandidateEvaluation:
    """Evaluate a candidate against the current snapshot. Requires
    computed_values (the candidate's actual values for today's universe)
    and optionally a target series for supervised checks.

    Sprint 2.6 provides quality + basic importance verdicts. Backtest /
    walk-forward evaluation lives in Sprint 9's Learning Engine — those
    fields remain False until then.
    """
    ev = CandidateEvaluation(candidate=candidate)

    # Governance completeness gate
    if not candidate.business_rationale.strip():
        ev.reasons.append("missing business_rationale")
    if not candidate.economic_intuition.strip():
        ev.reasons.append("missing economic_intuition")
    if not candidate.formula.strip():
        ev.reasons.append("missing formula")

    if computed_values is not None:
        s = computed_values.dropna()
        if len(s) < 10:
            ev.reasons.append("insufficient non-null values (<10)")
        elif s.nunique() < 2:
            ev.reasons.append("computed values are constant")
        else:
            ev.quality_ok = True

    if target is not None and computed_values is not None:
        m = pd.concat([computed_values, target], axis=1).dropna()
        if len(m) >= 20 and m.iloc[:, 0].nunique() >= 2 and m.iloc[:, 1].nunique() >= 2:
            corr = abs(float(m.corr().iloc[0, 1]))
            ev.importance_score = round(corr, 4)
            if corr >= 0.999:
                ev.reasons.append("perfect correlation with target — likely leakage")
                ev.verdict = "REJECT"

    if ev.verdict == "PENDING":
        # Sprint 2.6 only advances to READY_FOR_BACKTEST if governance + quality pass.
        if ev.quality_ok and candidate.business_rationale and candidate.economic_intuition:
            ev.verdict = "READY_FOR_BACKTEST"
        else:
            ev.verdict = "NEEDS_METADATA"
    return ev
