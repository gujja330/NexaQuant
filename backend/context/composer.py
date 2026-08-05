"""Context Intelligence Layer · composer.

Reads contributions from every registered adapter · composes into a
per-recommendation adjusted confidence + narrative + state suggestion.

Total adjustment cap: ±20 points (per spec · prevents whipsaw).

Phase 2A ships this with 4 adapters. Phase 2B extends adapters list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .adapter_base import ContextContribution


TOTAL_ADJ_CAP_PTS = 20.0     # max ±20 pts on any single recommendation

DEFAULT_WEIGHTS = {
    "macro":              0.15,
    "macro_event":        0.10,   # Fed/RBI/CPI pre-event penalty (uses macro bucket)
    "sector":             0.15,
    "overnight":          0.15,   # NEW · global overnight sector routing
    "breadth":            0.10,
    "news":               0.10,
    "earnings":           0.10,   # per-ticker earnings pre-event
    "vol_risk":           0.10,
    "currency":           0.05,
    "bond":               0.05,
    "institutional_flow": 0.10,
    "portfolio":          0.10,
}


@dataclass
class ContextAdjustment:
    ticker: str
    base_confidence:     float          # 0-100 · from runner's calibrated output
    adjusted_confidence: float          # 0-100 · after context adjustment · clamped
    total_drag_pts:      float          # signed · negative = drag · positive = boost
    contributions:       list           # list of ContextContribution dicts
    state_suggestion:    str            # BUY · WATCH · REVIEW · REDUCE · EXIT_URGENT
    story:               str            # one-line human summary
    metadata:            dict = field(default_factory=dict)


def _load_weights(root: Path) -> dict:
    p = root / "configs" / "context_weights.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"weights": DEFAULT_WEIGHTS,
                                          "total_cap_pts": TOTAL_ADJ_CAP_PTS},
                                        indent=2), encoding="utf-8")
        return DEFAULT_WEIGHTS
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("weights", DEFAULT_WEIGHTS)
    except Exception:
        return DEFAULT_WEIGHTS


def _classify_state(base: float, adjusted: float, contribs: list) -> str:
    """Map (base, adjusted, contributions) → state suggestion."""
    drag = adjusted - base
    critical_signals = sum(1 for c in contribs
                                    if getattr(c, "severity", "info") == "critical"
                                    and getattr(c, "data_available", False))
    if critical_signals >= 2:
        return "EXIT_URGENT"
    if drag <= -15:
        return "REDUCE"
    if drag <= -10:
        return "REVIEW"
    if drag <= -5:
        return "WATCH"
    return "BUY"      # no meaningful drag


def compose(root: Path, market: str, asof: str, rec: Mapping,
                adapters: Sequence) -> ContextAdjustment:
    """Compose one recommendation's context adjustment."""
    weights = _load_weights(root)
    base_conf = float(rec.get("calibrated_confidence") or
                          rec.get("confidence") or 0) * 100.0
    if base_conf > 100: base_conf = base_conf   # already pct
    elif base_conf <= 1 and base_conf > 0: base_conf = base_conf * 100

    contributions = []
    for adapter in adapters:
        try:
            c = adapter.contribute(root, market, asof, rec)
            if c is not None:
                contributions.append(c)
        except Exception as e:
            # Defensive · never let an adapter crash the composer
            contributions.append(ContextContribution(
                engine_name=getattr(adapter, "engine_name", "unknown"),
                contribution_pts=0.0,
                reason=f"adapter error · {type(e).__name__}: {e}",
                severity="info", data_available=False,
            ))

    # Sum contributions weighted (weight maps engine_name → weight)
    # Adapter names should match keys in DEFAULT_WEIGHTS (macro · sector · etc)
    raw_drag = 0.0
    for c in contributions:
        if not c.data_available: continue
        w = weights.get(c.engine_name, 0.0)
        raw_drag += c.contribution_pts * w * 10   # scale so ±1 contribution × 0.1 weight ≈ ±1 pt

    # Cap at ±TOTAL_ADJ_CAP_PTS
    capped_drag = max(-TOTAL_ADJ_CAP_PTS, min(TOTAL_ADJ_CAP_PTS, raw_drag))
    adjusted = max(0.0, min(100.0, base_conf + capped_drag))

    state = _classify_state(base_conf, adjusted, contributions)
    reasons = [c.reason for c in contributions
                    if c.data_available and abs(c.contribution_pts) > 0.5]
    story = " · ".join(reasons[:3]) if reasons else "no material context signals"

    return ContextAdjustment(
        ticker=rec.get("ticker") or "?",
        base_confidence=round(base_conf, 1),
        adjusted_confidence=round(adjusted, 1),
        total_drag_pts=round(adjusted - base_conf, 1),
        contributions=[{
            "engine": c.engine_name,
            "contribution_pts": round(c.contribution_pts, 2),
            "reason": c.reason,
            "severity": c.severity,
            "data_available": c.data_available,
        } for c in contributions],
        state_suggestion=state,
        story=story,
        metadata={"weights": weights, "raw_drag_pts": round(raw_drag, 2)},
    )


def emit_run(root: Path, market: str, asof: str,
                adjustments: list[ContextAdjustment]) -> Path:
    """Persist a full-market CIL run · shadow-only until Phase 2B activates it."""
    p = root / "reports" / "context" / f"cil_run_{market}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":         "aegis.context.cil.v0.1_scaffold",
        "asof":           asof,
        "market":         market,
        "generated_utc":  datetime.now(timezone.utc).isoformat(),
        "n":              len(adjustments),
        "phase":          "SCAFFOLD · Phase 2A activates 2026-09-09",
        "adjustments":    [
            {"ticker": a.ticker, "base": a.base_confidence,
             "adjusted": a.adjusted_confidence, "drag_pts": a.total_drag_pts,
             "state": a.state_suggestion, "story": a.story,
             "contributions": a.contributions}
            for a in adjustments
        ],
    }
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
