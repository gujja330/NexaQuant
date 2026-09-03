"""R3 Tier-3 · Pair Statistical Arbitrage · PDF R3 Tier-3.

    Engle-Granger cointegration → ADF stationarity test (p < 0.05)
    Entry:  |spread z| > 2.0
    Exit:   |spread z| < 0.5
    Stop:   |spread z| > 3.5

Pairs sourced from same KG communities · short-selling infrastructure
required (not present today) · biggest engineering lift per PDF.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T3-PAIR-STATARB",
    tier=3,
    name="Engle-Granger pair statistical arbitrage",
    description="Cointegration-tested pair spread trading · z-band entries",
    gate_precondition="R3 shadow ≥60 picks + KG communities persistent ≥90d + short-selling infrastructure present",
    pdf_reference="V2 §21 · R3 Tier-3 · pair stat-arb (biggest engineering lift · deferred)",
    additive_extension_id="R3-T3-PAIRS",
)

ENTRY_Z = 2.0
EXIT_Z = 0.5
STOP_Z = 3.5


def spread_zscore(px_a: list[float], px_b: list[float],
                  hedge_ratio: float) -> Optional[float]:
    """Latest z-score of spread = ln(px_a) − β·ln(px_b) over full series."""
    if not px_a or not px_b or len(px_a) != len(px_b): return None
    try:
        spreads = [math.log(a) - hedge_ratio * math.log(b) for a, b in zip(px_a, px_b)
                   if a > 0 and b > 0]
        if len(spreads) < 20: return None
        mu = sum(spreads) / len(spreads)
        var = sum((s - mu)**2 for s in spreads) / max(1, len(spreads) - 1)
        sd = math.sqrt(var)
        if sd <= 0: return 0.0
        return (spreads[-1] - mu) / sd
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=60)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market,
                              f"{reason} · Tier-3 requires ≥60 · plus short-sell infra not present",
                              extra_artifacts=[
                                  f"reports/research/r3/tier3/pair_stat_arb_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Source candidate pairs from KG communities · ADF test · z-band entry/exit rules",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
