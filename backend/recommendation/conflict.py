"""Conflict Resolution — detect and quantify model disagreement per ticker.

Reads a ticker's per-model score dict (from ensemble.json) → returns
model_agreement (fraction that agreed on the sign of the ensemble score)
plus a disagreement_flag when models materially disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConflictReport:
    n_models_scoring: int
    n_positive:       int
    n_negative:       int
    n_neutral:        int
    model_agreement:  float                   # 0..1
    dominant_side:    str                     # "positive" | "negative" | "neutral" | "split"
    disagreement_flag: bool
    disagreement_severity: str                # "none" | "minor" | "major"


NEUTRAL_BAND = 0.05           # scores within [-0.05, +0.05] treated as neutral
DISAGREE_THRESHOLD = 0.60     # agreement below this = disagreement_flag True
MAJOR_DISAGREE = 0.50         # near 50/50 split = major


def resolve_conflict(per_model_score: dict[str, float]) -> ConflictReport:
    """Given {model_id -> score}, compute agreement + disagreement."""
    scores = [v for v in per_model_score.values() if v is not None]
    if not scores:
        return ConflictReport(n_models_scoring=0, n_positive=0, n_negative=0, n_neutral=0,
                                model_agreement=0.0, dominant_side="neutral",
                                disagreement_flag=False, disagreement_severity="none")

    n_pos = sum(1 for s in scores if s > NEUTRAL_BAND)
    n_neg = sum(1 for s in scores if s < -NEUTRAL_BAND)
    n_neu = len(scores) - n_pos - n_neg
    n_total = len(scores)

    if n_pos > n_neg and n_pos > n_neu:
        dominant = "positive"
    elif n_neg > n_pos and n_neg > n_neu:
        dominant = "negative"
    elif n_neu >= max(n_pos, n_neg):
        dominant = "neutral"
    else:
        dominant = "split"

    # Agreement = max fraction on any one side (excluding neutrals from the base)
    directional = max(n_pos, n_neg)
    agreement = directional / n_total if n_total else 0.0
    # Boost agreement if one side dominates neutrals + opposite side
    if dominant in ("positive", "negative"):
        agreement = directional / max(1, n_total)

    disagreement = agreement < DISAGREE_THRESHOLD
    if agreement < MAJOR_DISAGREE:
        severity = "major"
    elif disagreement:
        severity = "minor"
    else:
        severity = "none"

    return ConflictReport(
        n_models_scoring=n_total,
        n_positive=n_pos, n_negative=n_neg, n_neutral=n_neu,
        model_agreement=round(agreement, 4),
        dominant_side=dominant,
        disagreement_flag=disagreement,
        disagreement_severity=severity,
    )
