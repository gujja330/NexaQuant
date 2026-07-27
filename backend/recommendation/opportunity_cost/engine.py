"""Opportunity Cost Engine · Constitution-compliant.

For every HOLD, expose:
  oc_next_best_ticker      : the highest-scoring non-held candidate in same/adjacent sector
  oc_expected_alpha_delta  : candidate_score - hold_current_score (pp equivalents)
  oc_reason_not_to_rotate  : short human-readable justification

Deterministic. Given identical inputs, produces identical enrichments.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.opportunity_cost.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.opportunity_cost.v1"


@dataclass(frozen=True)
class OpportunityCostEnrichment:
    hold_ticker: str
    oc_next_best_ticker: str | None
    oc_next_best_score: float | None
    oc_expected_alpha_delta: float | None
    oc_reason_not_to_rotate: str
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


class OpportunityCostEngine:
    """Rank candidates against each HOLD to expose opportunity cost."""

    def __init__(self, rotate_edge_threshold: float = 0.25) -> None:
        self.rotate_edge = rotate_edge_threshold

    def enrich(self,
                holds: Sequence[Mapping],
                candidates: Sequence[Mapping]) -> list[OpportunityCostEnrichment]:
        """holds: list of dicts with keys `ticker`, `current_score`, `sector`.
        candidates: list of dicts with keys `ticker`, `score`, `sector`."""
        held = {h["ticker"] for h in holds}
        # Filter to non-held candidates + rank by score
        ranked = sorted(
            [c for c in candidates if c.get("ticker") not in held],
            key=lambda c: -float(c.get("score", 0.0)),
        )
        out: list[OpportunityCostEnrichment] = []
        for h in holds:
            hold_score = float(h.get("current_score", 0.0))
            hold_sector = h.get("sector", "")
            # Prefer same-sector candidate; else best overall
            same_sector = next((c for c in ranked if c.get("sector") == hold_sector), None)
            best = same_sector or (ranked[0] if ranked else None)
            if best is None:
                out.append(OpportunityCostEnrichment(
                    hold_ticker=h["ticker"],
                    oc_next_best_ticker=None,
                    oc_next_best_score=None,
                    oc_expected_alpha_delta=None,
                    oc_reason_not_to_rotate="no candidate universe available",
                ))
                continue
            best_score = float(best.get("score", 0.0))
            edge = best_score - hold_score
            reason = self._reason(hold_score, best_score, edge, best.get("ticker"))
            out.append(OpportunityCostEnrichment(
                hold_ticker=h["ticker"],
                oc_next_best_ticker=best.get("ticker"),
                oc_next_best_score=round(best_score, 6),
                oc_expected_alpha_delta=round(edge, 6),
                oc_reason_not_to_rotate=reason,
            ))
        return out

    def _reason(self, hold_score: float, best_score: float, edge: float, best_ticker: str) -> str:
        if edge > self.rotate_edge:
            return (f"opportunity_cost_high · {best_ticker} score {best_score} vs hold {hold_score} "
                    f"(edge {edge:.4f} > rotate threshold {self.rotate_edge}) — recommend Capital Rotation review")
        if edge > 0:
            return (f"marginal edge {edge:.4f} vs {best_ticker} (below rotate threshold {self.rotate_edge}) — hold justified")
        return f"no better candidate available (best {best_ticker} edge {edge:.4f}) — hold optimal"


def enrich_holds(holds: Sequence[Mapping],
                  candidates: Sequence[Mapping],
                  rotate_edge_threshold: float = 0.25) -> list[dict]:
    """Convenience one-shot API returning a list of dicts."""
    eng = OpportunityCostEngine(rotate_edge_threshold=rotate_edge_threshold)
    return [asdict(e) for e in eng.enrich(holds, candidates)]
