"""R3 Tier-3 · GraphSAGE GNN · PDF R3 Tier-3.

    node features → neighbor aggregation → layer 1 → layer 2 → embedding →
    linear prediction head

Placed behind GBM + community-percentile per PDF because 581-node graph is
small and overfitting risk is high.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T3-GNN-GRAPHSAGE",
    tier=3,
    name="GraphSAGE GNN over 581-node KG",
    description="2-layer GraphSAGE · learned node embeddings · linear head",
    gate_precondition="R3 shadow ≥60 picks + Tier-2 community-percentile validated · KG per-node membership persistent ≥90d",
    pdf_reference="V2 §21 · R3 Tier-3 · GNN family (deliberately deferred pending Tier-2 evidence)",
    additive_extension_id="R3-T3-GNN",
)


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=60)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market,
                              f"{reason} · Tier-3 requires ≥60 shadow picks (not 20)",
                              extra_artifacts=[
                                  f"reports/research/r3/tier3/gnn_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Assemble node feature matrix · train 2-layer SAGE · WF eval · guard against 581-node overfit",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
