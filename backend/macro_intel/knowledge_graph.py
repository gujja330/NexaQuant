"""Macro Knowledge Graph — factor → affected sectors/industries/tickers.

Reusable dependency for every downstream engine. Sprint 6.5 emits the graph
as JSON; Sprint 9 AI Auditor uses it to explain "momentum failed because
oil↑ + rates↑ + macro shifted".

Sprint 6.5 baseline: builds the graph from the ACTIVE impact matrix + the
current commodity/currency/rate/vol state. Not a full knowledge-base — a
per-day snapshot of which macro factors currently matter.
"""
from __future__ import annotations

from backend.macro_intel.types import (
    CommodityImpact, MacroKnowledgeGraphEntry, MacroIntelligenceResult,
    CommodityReading, CurrencyReading, BondReading, VolatilityReading,
)


def _dir(chg_pct: float | None) -> str:
    if chg_pct is None: return "neutral"
    if chg_pct > 2: return "up"
    if chg_pct < -2: return "down"
    return "neutral"


def build_macro_knowledge_graph(commodities: list[CommodityReading],
                                   currencies: list[CurrencyReading],
                                   bonds: list[BondReading],
                                   volatility: VolatilityReading | None,
                                   active_impacts: list[CommodityImpact]) -> list[MacroKnowledgeGraphEntry]:
    """Return a list of MacroKnowledgeGraphEntry — one per currently-material macro factor."""
    entries: list[MacroKnowledgeGraphEntry] = []

    # ── Commodity entries via impact matrix ──────────────────
    for imp in active_impacts:
        entries.append(MacroKnowledgeGraphEntry(
            factor=imp.commodity,
            factor_kind="commodity",
            current_state=imp.direction,
            affected_sectors=list(imp.positive_sectors) + list(imp.negative_sectors),
            affected_industries=list(imp.mixed_sectors),
            direction="mixed" if imp.mixed_sectors else ("positive" if imp.direction == "down" and imp.positive_sectors else "negative"),
            evidence=imp.rationale,
        ))

    # ── Currency entries ────────────────────────────────────
    for c in currencies:
        state = _dir(c.chg_1w_pct)
        if state == "neutral": continue
        # DXY / UUP up → IT exporters benefit for India; Financials mixed for USA
        affected: list[str] = []
        direction = "mixed"
        evidence  = ""
        if c.symbol == "UUP":
            if state == "up":
                affected = ["Emerging Markets (negative)", "Financials", "IT (positive for exporters)"]
                direction = "mixed"
                evidence = "Strong dollar pressures emerging-market inflows; IT exporters benefit from realisation gains."
            else:
                affected = ["Emerging Markets (positive)", "Commodities (positive)"]
                direction = "positive"
                evidence = "Dollar weakness supports EM equity + commodity flows."
        if not affected:
            continue
        entries.append(MacroKnowledgeGraphEntry(
            factor=c.label, factor_kind="currency", current_state=state,
            affected_sectors=affected, direction=direction, evidence=evidence,
        ))

    # ── Rate / bond entries ─────────────────────────────────
    for b in bonds:
        if b.symbol != "^TNX": continue
        chg = b.chg_1m_bps
        if chg is None or abs(chg) < 15: continue
        state = "up" if chg > 0 else "down"
        if state == "up":
            entries.append(MacroKnowledgeGraphEntry(
                factor="10Y Treasury Yield", factor_kind="rate", current_state="up",
                affected_sectors=["Growth Stocks (negative)", "Utilities (negative)",
                                     "REITs (negative)", "Financials (positive)"],
                direction="mixed",
                evidence="Rising 10Y compresses long-duration valuations; net-interest-margin banks benefit.",
            ))
        else:
            entries.append(MacroKnowledgeGraphEntry(
                factor="10Y Treasury Yield", factor_kind="rate", current_state="down",
                affected_sectors=["Growth Stocks (positive)", "Utilities (positive)",
                                     "REITs (positive)", "Financials (negative)"],
                direction="mixed",
                evidence="Falling 10Y lifts long-duration valuations; net-interest-margin banks compressed.",
            ))

    # ── Volatility ──────────────────────────────────────────
    if volatility and volatility.regime in ("stress", "panic"):
        entries.append(MacroKnowledgeGraphEntry(
            factor="Equity Volatility", factor_kind="vol", current_state="up",
            affected_sectors=["Risk Assets (negative)", "Defensives (positive)",
                                 "Utilities (positive)", "Consumer Staples (positive)"],
            direction="mixed",
            evidence=f"VIX at {volatility.last:.1f} ({volatility.regime}) — flight to defensives typical.",
        ))
    return entries
