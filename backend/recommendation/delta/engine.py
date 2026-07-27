"""Recommendation Delta Engine · deterministic computation of yesterday-to-today
changes for every rec.

Consumes the previous day's `recommendations.json` snapshot and today's
`recommendations.json` (SSoT output) · emits per-ticker delta records with
prose reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.recommendation_delta.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.delta.v1"


def _num(v, default: float = 0.0) -> float:
    try: return float(v)
    except (TypeError, ValueError): return default


@dataclass(frozen=True)
class RecommendationDelta:
    ticker: str
    previous_rank: int | None
    current_rank: int | None
    rank_delta: int | None
    confidence_delta: float
    technical_delta: float
    fundamental_delta: float
    macro_delta: float
    sector_delta: float
    risk_delta: float
    rotation_delta: float
    previous_action: str | None
    current_action: str | None
    action_changed: bool
    reason_for_change: str
    ai_explanation_hint: str
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


def _index_by_ticker(recs: Sequence[Mapping]) -> dict[str, Mapping]:
    return {str(r.get("ticker", "")).strip(): r for r in recs if r.get("ticker")}


def _reason_prose(prev: Mapping | None, curr: Mapping) -> str:
    ticker = curr.get("ticker", "?")
    if prev is None:
        return f"{ticker} · NEW in universe · no prior snapshot"
    if prev.get("action") != curr.get("action"):
        return (f"{ticker} · action changed {prev.get('action')} -> {curr.get('action')} "
                f"(conf {_num(prev.get('confidence'))} -> {_num(curr.get('confidence'))})")
    r_delta = (_num(prev.get("rank"), 999) - _num(curr.get("rank"), 999))
    if abs(r_delta) >= 5:
        direction = "improved" if r_delta > 0 else "worsened"
        return f"{ticker} · rank {direction} by {abs(int(r_delta))} slots (score {curr.get('composite_decision_score')})"
    conf_delta = _num(curr.get("confidence")) - _num(prev.get("confidence"))
    if abs(conf_delta) >= 0.05:
        return f"{ticker} · confidence shifted {conf_delta:+.3f}"
    return f"{ticker} · steady state (small deltas)"


def _ai_hint(delta_pack: dict, action_changed: bool) -> str:
    if action_changed:
        return "explain the trigger for the action change and the risk of reversal"
    if abs(delta_pack.get("rank_delta") or 0) >= 5:
        return "explain what drove the rank movement (which factors carried the change)"
    if abs(delta_pack.get("confidence_delta") or 0) >= 0.05:
        return "explain confidence shift · which upstream models or features moved"
    return "narrate the steady state · confirm no material change vs prior day"


class DeltaEngine:
    """Deterministic Recommendation Delta Engine."""

    def compute(self,
                 today: Sequence[Mapping],
                 yesterday: Sequence[Mapping] | None) -> list[RecommendationDelta]:
        y_by = _index_by_ticker(yesterday) if yesterday else {}
        out: list[RecommendationDelta] = []
        for r in today:
            ticker = str(r.get("ticker", "")).strip()
            if not ticker: continue
            prev = y_by.get(ticker)
            curr_rank = int(r.get("rank")) if r.get("rank") is not None else None
            prev_rank = int(prev.get("rank")) if (prev and prev.get("rank") is not None) else None
            rank_delta = (prev_rank - curr_rank) if (prev_rank is not None and curr_rank is not None) else None
            confidence_delta = _num(r.get("confidence")) - _num(prev.get("confidence") if prev else 0.0)
            technical_delta = _num(r.get("composite_decision_score")) - _num(prev.get("composite_decision_score") if prev else 0.0)
            fundamental_delta = _num((r.get("dimensions") or {}).get("fundamental")) - _num((prev.get("dimensions", {}) if prev else {}).get("fundamental"))
            macro_delta = _num((r.get("dimensions") or {}).get("macro")) - _num((prev.get("dimensions", {}) if prev else {}).get("macro"))
            sector_delta = _num((r.get("dimensions") or {}).get("sector")) - _num((prev.get("dimensions", {}) if prev else {}).get("sector"))
            risk_delta = _num((r.get("dimensions") or {}).get("risk")) - _num((prev.get("dimensions", {}) if prev else {}).get("risk"))
            rotation_delta = _num(r.get("rotation_score")) - _num(prev.get("rotation_score") if prev else 0.0)
            action_changed = (prev is not None) and (str(prev.get("action")) != str(r.get("action")))
            pack = {"rank_delta": rank_delta, "confidence_delta": confidence_delta}
            out.append(RecommendationDelta(
                ticker=ticker,
                previous_rank=prev_rank,
                current_rank=curr_rank,
                rank_delta=rank_delta,
                confidence_delta=round(confidence_delta, 6),
                technical_delta=round(technical_delta, 6),
                fundamental_delta=round(fundamental_delta, 6),
                macro_delta=round(macro_delta, 6),
                sector_delta=round(sector_delta, 6),
                risk_delta=round(risk_delta, 6),
                rotation_delta=round(rotation_delta, 6),
                previous_action=(prev.get("action") if prev else None),
                current_action=r.get("action"),
                action_changed=action_changed,
                reason_for_change=_reason_prose(prev, r),
                ai_explanation_hint=_ai_hint(pack, action_changed),
            ))
        return out


def compute_deltas(today: Sequence[Mapping],
                    yesterday: Sequence[Mapping] | None) -> list[dict]:
    return [asdict(d) for d in DeltaEngine().compute(today, yesterday)]
