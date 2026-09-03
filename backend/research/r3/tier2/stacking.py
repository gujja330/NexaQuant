"""R3 Tier-2 · Stacking · CEO 2026-09-03 PDF R3 Tier-2.

Formula (from PDF):
    P_stacked = sigmoid(w1 · P_gbm + w2 · P_r2 + w3 · P_kg + b)

Weights (w1, w2, w3, b) are LEARNED via held-out logistic regression on
per-position win/loss labels · never hand-set.

Gate: BLOCKED-EVIDENCE until R3 shadow provides ≥20 picks (Day-30 gate).
When lifted, add: WF folds 252/63/21/5 + paired bootstrap 10k + DSR
deflation by n_trials.
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
    ticket_id="R3-T2-STACKING",
    tier=2,
    name="Stacking · sigmoid(w1·GBM + w2·R2 + w3·KG + b)",
    description="Learned meta-combiner over GBM · R2 base · KG-community score",
    gate_precondition="R3 shadow ledger ≥ 20 picks · Day-30 gate fired · GBM + R2 base + KG community available",
    pdf_reference="V2 §21 · R3 Tier-2 · stacking family",
    additive_extension_id="R3-T2-STACKING",
)


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z); return 1.0 / (1.0 + e)
    e = math.exp(z); return e / (1.0 + e)


def predict(w: list[float], gbm_p: float, r2_p: float, kg_p: float) -> float:
    """Apply learned stacking weights · deterministic scoring API."""
    if not w or len(w) != 4:
        return 0.5   # fallback · uninformative
    z = w[0] * float(gbm_p) + w[1] * float(r2_p) + w[2] * float(kg_p) + w[3]
    return _sigmoid(z)


def _fit_meta_logreg(X: list[list[float]], y: list[int]) -> list[float]:
    """Small batch-GD fit · no external lib · deterministic. w = [w1, w2, w3, b]."""
    if not X: return [0.0, 0.0, 0.0, 0.0]
    n = len(X); p = 4
    w = [0.0] * p; lr = 0.1; l2 = 0.001
    for _ in range(300):
        g = [0.0] * p
        for xi, yi in zip(X, y):
            z = w[0]*xi[0] + w[1]*xi[1] + w[2]*xi[2] + w[3]
            e = _sigmoid(z) - float(yi)
            g[0] += e * xi[0]; g[1] += e * xi[1]
            g[2] += e * xi[2]; g[3] += e
        for k in range(p):
            g[k] = g[k]/n + l2*w[k]
            w[k] -= lr * g[k]
    return w


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=20)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market, reason,
                              extra_artifacts=[
                                  f"reports/research/r3/tier2/stacking_{market}.json",
                                  f"configs/r3_stacking_weights_{market}.json",
                              ])
    # If unblocked: fit on OOF triples (gbm_p, r2_p, kg_p, win). Placeholder ·
    # real implementation joins OOF R3 predictions with R2 ensemble scores and
    # KG community-relative percentile.
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "note": "R3 shadow satisfied · run WF folds + paired bootstrap · deflate DSR",
        "next_step": "Assemble OOF (gbm_p, r2_p, kg_p, win) triples · fit logreg · report ECE + AUC + WF-Sharpe",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
