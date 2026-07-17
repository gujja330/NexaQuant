"""ARCH017A §9 — confidence math.

confidence = C_source × C_freshness × C_completeness × C_agreement
"""
from __future__ import annotations

from datetime import datetime, timezone


# ARCH017A §4.6 tier → C_source
_TIER_TO_C_SOURCE = {1: 1.00, 2: 0.85, 3: 0.70}


# ARCH017A §10.4 staleness thresholds (in days)
_CADENCE_STALE = {
    "real-time":  {"stale": 0.01, "failed": 0.16},   # 15m / 4h in days
    "intraday":   {"stale": 0.08, "failed": 1.0},
    "daily":      {"stale": 1.0,  "failed": 2.0},
    "weekly":     {"stale": 8.0,  "failed": 15.0},
    "monthly":    {"stale": 40.0, "failed": 60.0},
    "quarterly":  {"stale": 100.0, "failed": 180.0},
}


def c_source(tier: int) -> float:
    return _TIER_TO_C_SOURCE.get(tier, 0.5)


def c_freshness(asof_utc_iso: str, cadence: str = "daily", ref_utc_iso: str | None = None) -> float:
    """Age of the observation relative to expected cadence.

    fresh                   → 1.0
    at expected cadence     → 0.9
    at 'stale' threshold    → 0.5
    at 'failed' threshold   → 0.0
    """
    asof = _parse(asof_utc_iso)
    ref = _parse(ref_utc_iso) if ref_utc_iso else datetime.now(timezone.utc)
    age_days = (ref - asof).total_seconds() / 86400.0
    thr = _CADENCE_STALE.get(cadence, _CADENCE_STALE["daily"])

    # For 'daily', we expect the observation to be at most 1 session old.
    # Weekend context: an observation older than 3 calendar days on Monday
    # morning is still fresh. Approximation: allow up to 2× the stale
    # threshold before starting decay when cadence is daily and age < stale*2.
    if cadence == "daily" and age_days <= 3.0:
        return 1.0
    if age_days <= thr["stale"]:
        return 1.0
    if age_days >= thr["failed"]:
        return 0.0
    # Linear decay between stale (=0.5) and failed (=0.0)
    span = thr["failed"] - thr["stale"]
    return max(0.0, 0.5 * (thr["failed"] - age_days) / span)


def c_completeness(present: int, expected: int) -> float:
    if expected <= 0:
        return 1.0
    return max(0.0, min(1.0, present / expected))


def c_agreement(agree_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 1.0
    return max(0.0, min(1.0, agree_count / total_count))


def combine(c_src: float, c_fresh: float, c_comp: float, c_agree: float) -> float:
    return max(0.0, min(1.0, c_src * c_fresh * c_comp * c_agree))


def _parse(iso: str) -> datetime:
    """Robust ISO parser handling both 'Z' and offset formats."""
    s = iso.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def tier_from_downstream(confidence: float) -> str:
    """ARCH017A §9.2 response tier."""
    if confidence >= 0.9:
        return "High"
    if confidence >= 0.7:
        return "Medium"
    if confidence >= 0.5:
        return "Low"
    if confidence > 0:
        return "VeryLow"
    return "Failed"
