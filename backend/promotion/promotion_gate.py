"""Promotion Gate — enforces the human-in-the-loop rule.

AI can propose. AI can hypothesize. AI can evaluate. AI CANNOT promote.

`check_promotion()` runs the criteria check and returns a PASS/FAIL with
reasons. Only after PASS does an operator invoke `approve_feature()` or
`approve_model()`, which stamps `approved: True` in the appropriate
registry entry.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


PROMOTION_LEDGER = "promotion_ledger.jsonl"


@dataclass
class PromotionCriteria:
    """Thresholds for promotion. Operator can tune."""
    min_walk_forward_windows:     int   = 3       # at least 3 non-overlapping WF windows
    min_significance_p_value:     float = 0.05
    min_stability_score:          float = 0.60    # 0..1, cross-regime stability
    require_backtest:             bool  = True
    require_business_rationale:   bool  = True
    require_economic_intuition:   bool  = True


@dataclass
class PromotionDecision:
    kind:        str                   # "feature" | "model"
    subject_id:  str
    verdict:     str                   # "READY_FOR_APPROVAL" | "BLOCKED"
    reasons:     list[str] = field(default_factory=list)
    evidence:    dict = field(default_factory=dict)


def check_promotion(kind: str, subject_id: str,
                       criteria: PromotionCriteria | None = None,
                       evidence: dict | None = None) -> PromotionDecision:
    """Evaluate whether a candidate/model is READY_FOR_APPROVAL.

    Returns READY_FOR_APPROVAL only if every criterion is satisfied.
    An operator then calls approve_feature() / approve_model() to complete.
    """
    c = criteria or PromotionCriteria()
    e = evidence or {}
    d = PromotionDecision(kind=kind, subject_id=subject_id,
                            verdict="READY_FOR_APPROVAL", reasons=[], evidence=e)

    # ── Metadata checks (applies to features) ─────────────────
    if kind == "feature":
        if c.require_business_rationale and not e.get("business_rationale"):
            d.reasons.append("missing business_rationale")
        if c.require_economic_intuition and not e.get("economic_intuition"):
            d.reasons.append("missing economic_intuition")
        if not e.get("formula"):
            d.reasons.append("missing formula")

    # ── Walk-forward evidence ─────────────────────────────────
    wf = e.get("walk_forward", {}) or {}
    wf_windows = int(wf.get("n_windows", 0))
    if wf_windows < c.min_walk_forward_windows:
        d.reasons.append(f"only {wf_windows} walk-forward window(s), need {c.min_walk_forward_windows}")

    # ── Statistical significance ─────────────────────────────
    p_val = wf.get("p_value")
    if p_val is None:
        d.reasons.append("no p-value in walk-forward evidence")
    elif p_val > c.min_significance_p_value:
        d.reasons.append(f"p-value {p_val:.4f} > threshold {c.min_significance_p_value}")

    # ── Stability across regimes ─────────────────────────────
    stab = wf.get("stability_score")
    if stab is None:
        d.reasons.append("no stability_score in evidence")
    elif stab < c.min_stability_score:
        d.reasons.append(f"stability {stab:.2f} < threshold {c.min_stability_score:.2f}")

    # ── Backtest ─────────────────────────────────────────────
    if c.require_backtest:
        bt = e.get("backtest", {}) or {}
        if not bt.get("passed"):
            d.reasons.append("backtest evidence missing or not passed")

    if d.reasons:
        d.verdict = "BLOCKED"
    return d


def _append_ledger(repo_root: Path, entry: dict) -> None:
    p = Path(repo_root) / PROMOTION_LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    entry["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def approve_feature(repo_root: Path, feature_name: str, approved_by: str,
                      decision: PromotionDecision) -> dict:
    """Operator promotion for a candidate feature.

    Precondition: decision.verdict must be READY_FOR_APPROVAL.
    """
    if decision.verdict != "READY_FOR_APPROVAL":
        raise ValueError(f"cannot approve {feature_name}: verdict is {decision.verdict}, "
                          f"blockers: {decision.reasons}")
    entry = {
        "kind":         "feature",
        "subject_id":   feature_name,
        "approved_by":  approved_by,
        "approved_on":  date.today().isoformat(),
        "criteria":     asdict(decision),
    }
    _append_ledger(repo_root, entry)
    return entry


def approve_model(repo_root: Path, model_id: str, approved_by: str,
                    decision: PromotionDecision) -> dict:
    if decision.verdict != "READY_FOR_APPROVAL":
        raise ValueError(f"cannot approve model {model_id}: verdict is {decision.verdict}, "
                          f"blockers: {decision.reasons}")
    entry = {
        "kind":         "model",
        "subject_id":   model_id,
        "approved_by":  approved_by,
        "approved_on":  date.today().isoformat(),
        "criteria":     asdict(decision),
    }
    _append_ledger(repo_root, entry)
    return entry
