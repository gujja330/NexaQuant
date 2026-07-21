"""
Sprint 7.6 · Data quality scoring.

Every historical record produced by the replay engine carries a
`data_quality_score` (0-100). Sprint 8 (Walk-Forward) and Sprint 9
(AI Auditor) can down-weight low-quality days instead of treating
all history equally.

Score composition (out of 100):
    50 · completeness (fraction of expected fields present, non-null, non-zero)
    30 · freshness   (100 - 5*days_stale, floored at 0)
    20 · sources     (min(source_count, 5) * 4)
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, Optional

from .types import DataQuality


def compute_row_quality_score(
    payload: Dict[str, Any],
    *,
    expected_fields: Iterable[str],
    freshness_days_before_asof: int = 0,
    source_count: int = 1,
    treat_zero_as_missing: bool = False,
) -> DataQuality:
    """
    Score a single history row's data quality.

    - `payload`: the flattened row dict about to be persisted
    - `expected_fields`: the set of keys we expect populated
    - `freshness_days_before_asof`: 0 = same-day input, higher = staler
    - `source_count`: how many distinct raw sources contributed
    - `treat_zero_as_missing`: for macro/factor rows where 0.0 often means
       "unavailable" rather than a real reading
    """
    expected = list(expected_fields)
    n_expected = max(len(expected), 1)
    notes: list[str] = []

    n_present = 0
    for k in expected:
        v = payload.get(k)
        if v is None:
            continue
        if treat_zero_as_missing and isinstance(v, (int, float)) and v == 0:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        n_present += 1

    completeness = n_present / n_expected
    completeness_pts = 50 * completeness

    freshness_pts = max(0, 30 - 5 * max(0, freshness_days_before_asof))

    sources_pts = min(source_count, 5) * 4          # 5+ sources → full 20

    score = int(round(completeness_pts + freshness_pts + sources_pts))
    score = max(0, min(100, score))

    if completeness < 0.5:
        notes.append(f"completeness low: {n_present}/{n_expected}")
    if freshness_days_before_asof > 3:
        notes.append(f"stale input: {freshness_days_before_asof}d before asof")
    if source_count < 2:
        notes.append(f"single source only")

    return DataQuality(
        score=score,
        completeness=completeness,
        freshness_days_before_asof=freshness_days_before_asof,
        source_count=source_count,
        verdict=quality_verdict(score),
        notes=notes,
    )


def quality_verdict(score: int) -> str:
    """Score bands → institutional-usability verdict."""
    if score >= 85:
        return "high"
    if score >= 65:
        return "medium"
    if score >= 40:
        return "low"
    return "unusable"


def batch_average_quality(scores: Iterable[Optional[int]]) -> float:
    """Average non-None scores; 0.0 if list empty."""
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0.0
