"""R3 Tier-2 · Multi-Horizon Consensus · PDF R3 Tier-2.

Combines forecasts across 5/10/20/60-day horizons weighted by each
horizon's trailing IC.

    Consensus_p = Σ IC(h) · p_h(win_at_h)  /  Σ IC(h)

If short and long horizons disagree · flag SIGNAL_DISPUTED (research-only
flag · never automatic sizing rule).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T2-MULTI-HORIZON",
    tier=2,
    name="Multi-Horizon Consensus (5/10/20/60d fused by IC)",
    description="IC-weighted fusion of per-horizon win probability + disagreement flag",
    gate_precondition="R3 shadow ≥20 picks · per-horizon IC trailing window ≥60 obs",
    pdf_reference="V2 §21 · R3 Tier-2 · multi-horizon consensus",
    additive_extension_id="R3-T2-MULTI-HORIZON",
)


def consensus_probability(per_horizon_p: dict[int, float],
                          per_horizon_ic: dict[int, float]) -> Optional[float]:
    """IC-weighted average · returns None if all ICs zero/absent."""
    if not per_horizon_p: return None
    weights = {h: max(0.0, float(per_horizon_ic.get(h, 0.0))) for h in per_horizon_p}
    s = sum(weights.values())
    if s <= 0: return None
    return sum(float(p) * weights[h] for h, p in per_horizon_p.items()) / s


def disputed_flag(per_horizon_p: dict[int, float],
                  threshold_span: float = 0.30) -> bool:
    """SIGNAL_DISPUTED when max−min across horizons exceeds threshold_span."""
    vs = [float(p) for p in per_horizon_p.values() if p is not None]
    if len(vs) < 2: return False
    return (max(vs) - min(vs)) >= threshold_span


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=20)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market, reason,
                              extra_artifacts=[
                                  f"reports/research/r3/tier2/multi_horizon_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Compute per-horizon rolling IC from Signal Ledger fwd_5/10/20/60d columns · fuse",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
