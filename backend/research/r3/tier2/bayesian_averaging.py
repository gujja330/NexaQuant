"""R3 Tier-2 · Bayesian Model Averaging (BMA) · CEO 2026-09-03 PDF R3 Tier-2.

Weights each candidate model by its posterior evidence (marginal likelihood
proxy · we use trailing OOF log-loss as substitute) rather than a single
maximum-likelihood winner.

    p(win | x) = Σ P(model_k | data) · p(win | x, model_k)

Gate: BLOCKED-EVIDENCE until R3 shadow ≥ 20 picks · Day-30 fired.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T2-BMA",
    tier=2,
    name="Bayesian Model Averaging",
    description="Posterior-weighted ensemble across candidate R3 model families",
    gate_precondition="R3 shadow ≥20 picks · multiple candidate models trained · OOF log-loss per model available",
    pdf_reference="V2 §21 · R3 Tier-2 · Bayesian averaging",
    additive_extension_id="R3-T2-BMA",
)


def bma_weights(model_oof_logloss: dict[str, float],
                prior: dict[str, float] | None = None) -> dict[str, float]:
    """Convert per-model trailing OOF log-loss into posterior weights.

    Proxy: log-marginal ≈ −loss · softmax(−loss + log(prior)).
    """
    if not model_oof_logloss: return {}
    prior = prior or {m: 1.0/len(model_oof_logloss) for m in model_oof_logloss}
    logits = {m: -float(loss) + math.log(prior.get(m, 1e-9))
              for m, loss in model_oof_logloss.items()}
    mx = max(logits.values())
    exps = {m: math.exp(v - mx) for m, v in logits.items()}
    s = sum(exps.values())
    return {m: e / s for m, e in exps.items()}


def bma_predict(per_model_p: dict[str, float], weights: dict[str, float]) -> float:
    return sum(float(per_model_p.get(m, 0.5)) * w for m, w in weights.items())


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=20)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market, reason,
                              extra_artifacts=[
                                  f"reports/research/r3/tier2/bma_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Collect OOF log-loss per candidate model · compute posterior weights · WF eval",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
