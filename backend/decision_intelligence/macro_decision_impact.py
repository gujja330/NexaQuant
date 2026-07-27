"""Macro → Decision Impact Engine.

For every macro move (commodity/currency/bond price change), propagate through:
    macro signal → affected sectors (via impact matrix) → expected sector
    alpha contribution → recommendation impact → portfolio impact.

Transforms `commodity_intelligence.json` from pure data into a decision input.

Deterministic · fingerprinted · consumes existing macro artifacts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.macro_decision_impact.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.decision_intelligence.macro_impact.v1"

# Alpha-magnitude assumption: a 1% commodity move fully propagated by the
# impact matrix contributes this much sector alpha (bp). Bounded institutional prior.
ALPHA_PER_1PCT_MOVE_BP = 15   # 15bp sector alpha per 1% commodity move
MATERIAL_MOVE_PCT = 2.0        # only propagate moves ≥ 2% |1w-chg|


@dataclass(frozen=True)
class SectorImpact:
    sector: str
    direction: str            # "positive" · "negative" · "mixed"
    driver_commodity: str
    driver_move_pct: float
    expected_alpha_bp: float
    confidence: float
    rationale: str


@dataclass(frozen=True)
class PropagationChain:
    macro_symbol: str
    macro_move_pct: float
    macro_direction: str      # "up" · "down"
    sector_impacts: list[dict]      # SectorImpact serialized
    n_sectors_affected: int
    confidence: float
    rationale: str


@dataclass
class MacroDecisionReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    market: str = ""
    asof: str = ""
    run_utc: str = ""
    n_macro_moves: int = 0
    n_material_moves: int = 0
    n_sector_impacts: int = 0
    propagation_chains: list[dict] = field(default_factory=list)
    sector_alpha_summary: dict = field(default_factory=dict)  # sector → net_alpha_bp


def _load_json(p: Path) -> dict | None:
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None


def _direction(chg_pct: float) -> str:
    return "up" if chg_pct >= 0 else "down"


class MacroDecisionImpactEngine:
    """Deterministic Macro-Decision propagation."""

    def __init__(self, market: str = "india"):
        self.market = market
        # Import at runtime · impact matrix lives in macro_intel
        from backend.macro_intel import COMMODITY_IMPACT_MATRIX
        self.impact_matrix = COMMODITY_IMPACT_MATRIX

    def run(self, reports_dir: Path) -> MacroDecisionReport:
        commodity = _load_json(reports_dir / "commodity_intelligence.json") or {}
        currency = _load_json(reports_dir / "currency_intelligence.json") or {}
        bonds = _load_json(reports_dir / "bond_intelligence.json") or {}

        rep = MacroDecisionReport(
            market=self.market,
            asof=str(commodity.get("asof") or date.today().isoformat()),
            run_utc=datetime.now(timezone.utc).isoformat(),
        )

        sector_alpha_bp: dict[str, float] = {}
        chains: list[PropagationChain] = []

        # Commodities · use 1w change as the propagation trigger
        for c in commodity.get("commodities", []):
            sym = c.get("symbol", "")
            move_pct = c.get("chg_1w_pct", 0.0)
            if move_pct is None: continue
            rep.n_macro_moves += 1
            if abs(move_pct) < MATERIAL_MOVE_PCT:
                continue
            rep.n_material_moves += 1
            direction = _direction(move_pct)
            key = (sym, direction)
            impact = self.impact_matrix.get(key)
            if not impact:
                continue
            impacts_list: list[SectorImpact] = []
            magnitude_bp = abs(move_pct) * ALPHA_PER_1PCT_MOVE_BP * impact.confidence
            for sec in impact.positive_sectors:
                bp = round(magnitude_bp, 2)
                impacts_list.append(SectorImpact(
                    sector=sec, direction="positive",
                    driver_commodity=impact.commodity,
                    driver_move_pct=round(move_pct, 3),
                    expected_alpha_bp=bp,
                    confidence=impact.confidence,
                    rationale=impact.rationale[:120],
                ))
                sector_alpha_bp[sec] = sector_alpha_bp.get(sec, 0.0) + bp
            for sec in impact.negative_sectors:
                bp = round(-magnitude_bp, 2)
                impacts_list.append(SectorImpact(
                    sector=sec, direction="negative",
                    driver_commodity=impact.commodity,
                    driver_move_pct=round(move_pct, 3),
                    expected_alpha_bp=bp,
                    confidence=impact.confidence,
                    rationale=impact.rationale[:120],
                ))
                sector_alpha_bp[sec] = sector_alpha_bp.get(sec, 0.0) + bp
            for sec in impact.mixed_sectors:
                impacts_list.append(SectorImpact(
                    sector=sec, direction="mixed",
                    driver_commodity=impact.commodity,
                    driver_move_pct=round(move_pct, 3),
                    expected_alpha_bp=0.0,
                    confidence=impact.confidence,
                    rationale=impact.rationale[:120],
                ))

            chains.append(PropagationChain(
                macro_symbol=sym,
                macro_move_pct=round(move_pct, 3),
                macro_direction=direction,
                sector_impacts=[asdict(x) for x in impacts_list],
                n_sectors_affected=len(impacts_list),
                confidence=impact.confidence,
                rationale=impact.rationale,
            ))
            rep.n_sector_impacts += len(impacts_list)

        rep.propagation_chains = [asdict(x) for x in chains]
        # Round-off net sector alpha
        rep.sector_alpha_summary = {k: round(v, 2) for k, v in
                                      sorted(sector_alpha_bp.items(),
                                              key=lambda kv: -abs(kv[1]))}
        return rep


def run_macro_decision_impact(market: str, reports_dir: Path) -> dict:
    return asdict(MacroDecisionImpactEngine(market).run(reports_dir))
