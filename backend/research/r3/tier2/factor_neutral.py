"""R3 Tier-2 · Factor-Neutral / Market-Neutral scoring · PDF R3 Tier-2.

    Residual_Score = Base_Score − Σ β_k · Factor_Exposure_k

β estimated daily via cross-sectional regression against size / value /
momentum factor scores.

Purpose: determine whether apparent Sector/Cap performance is genuine
stock selection or uncompensated factor exposure.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T2-FACTOR-NEUTRAL",
    tier=2,
    name="Factor-Neutral · residual = base − Σβ·exposure",
    description="Cross-sectional regression to strip size/value/momentum exposures",
    gate_precondition="R3 shadow ≥20 picks · cap + value + momentum factors PIT-available",
    pdf_reference="V2 §21 · R3 Tier-2 · factor-neutral scoring",
    additive_extension_id="R3-T2-FACTOR-NEUTRAL",
)


def compute_residual_score(base_score: float, factor_exposures: dict[str, float],
                           betas: dict[str, float]) -> float:
    """Point-in-time residual · positive residual = alpha beyond factors."""
    proj = sum(betas.get(k, 0.0) * float(v) for k, v in factor_exposures.items())
    return float(base_score) - proj


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=20)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market, reason,
                              extra_artifacts=[
                                  f"reports/research/r3/tier2/factor_neutral_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Build daily cross-sectional regression · β vector time-series · WF eval",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
