"""Commodity → sector impact matrix.

Deterministic template lookup — a curated reference derived from institutional
research literature (Damodaran, Fama-French sector papers, RBI/Fed staff notes).
Every entry has a confidence score reflecting how well-documented the relationship is.

Sprint 9 AI Auditor may propose additions/adjustments via promotion gate — the
matrix is operator-owned in `configs/macro_intel_config.yaml` for tuning.
"""
from __future__ import annotations

from backend.macro_intel.types import CommodityImpact, CommodityReading


# ── The matrix ───────────────────────────────────────────────────
# Each entry: (commodity, direction) → CommodityImpact template
COMMODITY_IMPACT_MATRIX: dict[tuple[str, str], CommodityImpact] = {

    # ── Crude Oil ────────────────────────────────────────────────
    ("CL=F", "up"): CommodityImpact(
        commodity="WTI Crude",
        direction="up",
        positive_sectors=["Energy", "Oil Producers", "Oil Services"],
        negative_sectors=["Airlines", "Transportation", "Consumer Discretionary",
                            "Paints", "FMCG", "Auto", "Logistics", "Chemicals"],
        mixed_sectors=["Refiners"],       # margin compression + higher realisations
        confidence=0.92,
        rationale=("Rising oil raises transportation + input costs; erodes margins for "
                    "downstream consumers; boosts upstream producers. Historically the "
                    "single most reliable commodity → sector relationship."),
    ),
    ("CL=F", "down"): CommodityImpact(
        commodity="WTI Crude",
        direction="down",
        positive_sectors=["Airlines", "Transportation", "Consumer Discretionary",
                            "Paints", "FMCG", "Auto", "Logistics"],
        negative_sectors=["Energy", "Oil Producers", "Oil Services"],
        confidence=0.90,
        rationale=("Falling oil reduces input costs; downstream margins expand. "
                    "Upstream capex compresses."),
    ),

    # ── Natural Gas ──────────────────────────────────────────────
    ("NG=F", "up"): CommodityImpact(
        commodity="Natural Gas",
        direction="up",
        positive_sectors=["Gas Producers"],
        negative_sectors=["Fertilizers", "Chemicals", "Utilities", "Power-intensive Industries"],
        confidence=0.85,
        rationale="Nat gas feedstock for urea + power → margin pressure on fertilizers, utilities.",
    ),

    # ── Gold ─────────────────────────────────────────────────────
    ("GC=F", "up"): CommodityImpact(
        commodity="Gold",
        direction="up",
        positive_sectors=["Gold Miners", "Precious Metals"],
        negative_sectors=[],    # Gold jewelry demand may soften but sector-level impact minor
        mixed_sectors=["Jewelry Retailers"],
        confidence=0.75,
        rationale=("Gold rally often coincides with risk-off equity sentiment; gold miners "
                    "benefit directly. Historically inverse-correlated with USD."),
    ),
    ("GC=F", "down"): CommodityImpact(
        commodity="Gold",
        direction="down",
        positive_sectors=["Jewelry Retailers"],
        negative_sectors=["Gold Miners"],
        confidence=0.70,
        rationale="Gold weakness usually risk-on; jewelry demand recovers.",
    ),

    # ── Copper ───────────────────────────────────────────────────
    ("HG=F", "up"): CommodityImpact(
        commodity="Copper",
        direction="up",
        positive_sectors=["Mining", "Copper Producers", "Base Metals"],
        negative_sectors=["Electrical Equipment", "Cables", "Electronics", "EV Assemblers"],
        confidence=0.80,
        rationale="Dr Copper. Global-growth proxy. Producers win; downstream inputs squeeze.",
    ),

    # ── Silver ───────────────────────────────────────────────────
    ("SI=F", "up"): CommodityImpact(
        commodity="Silver",
        direction="up",
        positive_sectors=["Silver Miners", "Precious Metals"],
        negative_sectors=["Solar Manufacturers", "Photovoltaics"],
        confidence=0.65,
    ),

    # ── Brent (parallel to WTI) ──────────────────────────────────
    ("BZ=F", "up"): CommodityImpact(
        commodity="Brent Crude",
        direction="up",
        positive_sectors=["Energy", "Oil Producers"],
        negative_sectors=["Airlines", "Transportation", "Auto", "Paints"],
        confidence=0.90,
    ),
    ("BZ=F", "down"): CommodityImpact(
        commodity="Brent Crude",
        direction="down",
        positive_sectors=["Airlines", "Transportation", "Auto", "Paints"],
        negative_sectors=["Energy", "Oil Producers"],
        confidence=0.88,
    ),
}


def apply_impact_matrix(commodities: list[CommodityReading],
                          threshold_pct: float = 3.0) -> list[CommodityImpact]:
    """Return the active impacts: commodities whose 1-week move exceeds threshold."""
    active: list[CommodityImpact] = []
    for c in commodities:
        chg_1w = c.chg_1w_pct
        if chg_1w is None: continue
        if chg_1w > threshold_pct:
            imp = COMMODITY_IMPACT_MATRIX.get((c.symbol, "up"))
            if imp: active.append(imp)
        elif chg_1w < -threshold_pct:
            imp = COMMODITY_IMPACT_MATRIX.get((c.symbol, "down"))
            if imp: active.append(imp)
    return active
