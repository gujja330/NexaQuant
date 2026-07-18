"""Adaptive Rec Engine v2.1 · Intelligence Fusion.

Combines the 10 dimensions (dimensions.py) into a single Investment
Intelligence Score with configurable weights and a deterministic
decision mapping.

Every input is bounded; every weight is transparent; no hardcoded
per-ticker tuning."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from adaptive_rec_v2.lib.dimensions import DimensionScore


_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"

# Default weights (sum ~ 1.0). Overridable via
# reports/fusion_weights.json or a caller-supplied dict.
DEFAULT_WEIGHTS = {
    "research":         0.15,
    "historical":       0.15,
    "validation":       0.10,
    "risk":             0.15,
    "portfolio_fit":    0.10,
    "knowledge_graph":  0.05,
    "dna":              0.10,
    "calibration":      0.05,
    "learning":         0.05,
    "explainability":   0.05,   # sum 0.95 with 0.05 slack
}


# Decision thresholds on the fused 0-100 score. Deterministic.
DECISION_THRESHOLDS = [
    (85, "Strong-Buy"),
    (70, "Buy"),
    (55, "Hold"),
    (40, "Reduce"),
    (0,  "Avoid"),
]


def load_weights() -> dict[str, float]:
    """Load weights from reports/fusion_weights.json if present, else defaults."""
    p = REPORTS / "fusion_weights.json"
    if p.exists():
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(j, dict) and all(k in DEFAULT_WEIGHTS for k in j):
                merged = {**DEFAULT_WEIGHTS, **j}
                return merged
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def fuse(dims: list[DimensionScore],
           weights: dict[str, float] | None = None) -> dict:
    """Compute the Investment Intelligence Score.

    - Uses only dimensions with score != None (available signals).
    - Renormalises weights across available dimensions.
    - Returns the fused score + decision + per-dimension contributions."""
    weights = weights or load_weights()

    available = [d for d in dims if d.score is not None]
    if not available:
        return {
            "intelligence_score":  None,
            "decision":            "INSUFFICIENT_EVIDENCE",
            "n_dimensions_used":   0,
            "n_dimensions_missing": len(dims),
            "contributions":       [],
            "weights_used":        {},
        }

    used_weights = {d.name: weights.get(d.name, 0.0) for d in available}
    w_sum = sum(used_weights.values()) or 1.0
    normalised = {k: v / w_sum for k, v in used_weights.items()}

    contributions = []
    fused_score = 0.0
    for d in available:
        w = normalised[d.name]
        contribution = w * d.score
        fused_score += contribution
        contributions.append({
            "name":         d.name,
            "score":        d.score,
            "weight":       round(used_weights[d.name], 4),
            "weight_norm":  round(w, 4),
            "contribution": round(contribution, 3),
            "source":       d.source,
        })

    contributions.sort(key=lambda c: -c["contribution"])

    fused = round(min(100.0, max(0.0, fused_score)), 2)
    decision = _decision_for(fused)

    return {
        "intelligence_score":     fused,
        "decision":               decision,
        "n_dimensions_used":      len(available),
        "n_dimensions_missing":   len(dims) - len(available),
        "missing_dimensions":     [d.name for d in dims if d.score is None],
        "contributions":          contributions,
        "top_contributors":       [c["name"] for c in contributions[:3]],
        "bottom_contributors":    [c["name"] for c in contributions[-3:]],
        "weights_used":           used_weights,
    }


def _decision_for(score: float) -> str:
    for threshold, label in DECISION_THRESHOLDS:
        if score >= threshold:
            return label
    return "Avoid"


def why_not_stronger(dims: list[DimensionScore]) -> list[dict]:
    """List up to 3 dimensions holding the score back (available + lowest)."""
    avail = [d for d in dims if d.score is not None]
    avail.sort(key=lambda d: d.score)
    return [{
        "name":  d.name,
        "score": d.score,
        "why":   d.explanation,
    } for d in avail[:3]]


def why_this_recommendation(dims: list[DimensionScore]) -> list[dict]:
    """List up to 3 dimensions supporting the score (available + highest)."""
    avail = [d for d in dims if d.score is not None]
    avail.sort(key=lambda d: -d.score)
    return [{
        "name":  d.name,
        "score": d.score,
        "why":   d.explanation,
    } for d in avail[:3]]
