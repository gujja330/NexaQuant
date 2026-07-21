"""AI Macro Analyst v1.0 — descriptive audit of macro state.

Reads MacroIntelligenceResult. Emits:
  - Regime narrative + macro score
  - Volatility state + VIX level
  - Active commodity impacts (which commodities are moving material amounts)
  - Sector rotation call (leaders + laggards)
  - Central bank state
  - Yield curve inversion warning
  - Currency pressure narrative

Never emits buy/sell/promoted/approved keys (contract-tested).
"""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput
from backend.macro_intel.types import MacroIntelligenceResult

VERSION = "v1.0"


def run(result: MacroIntelligenceResult, market_name: str,
         asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Regime headline
    if result.macro_regime:
        mr = result.macro_regime
        findings.append({
            "type":             "macro_regime",
            "primary":          mr.primary_regime,
            "secondary":        mr.secondary_regime,
            "confidence":       mr.confidence,
            "macro_score":      mr.macro_score,
            "evidence":         mr.evidence,
        })

    # Volatility
    if result.volatility:
        v = result.volatility
        findings.append({
            "type":    "volatility",
            "symbol":  v.symbol,
            "level":   v.last,
            "regime":  v.regime,
            "chg_1m_pct": v.chg_1m_pct,
        })

    # Central bank
    if result.central_bank:
        cb = result.central_bank
        findings.append({
            "type":              "central_bank_state",
            "bank":              cb.bank,
            "rate_cycle":        cb.rate_cycle,
            "yield_curve_slope": cb.yield_curve_slope,
            "inversion":         cb.inversion,
            "liquidity_score":   cb.liquidity_score,
            "notes":             cb.notes,
        })

    # Yield curve inversion — surface as its own signal
    if result.central_bank and result.central_bank.inversion:
        findings.append({
            "type":               "yield_curve_inversion",
            "note":               "10Y-2Y inversion detected — historical recession leading indicator (2Y proxied by ^FVX/^IRX).",
            "curve_slope_bps":    result.central_bank.yield_curve_slope,
        })

    # Active commodity impacts
    for imp in (result.active_impacts or [])[:5]:
        findings.append({
            "type":              "commodity_impact",
            "commodity":         imp.commodity,
            "direction":         imp.direction,
            "positive_sectors":  imp.positive_sectors,
            "negative_sectors":  imp.negative_sectors,
            "confidence":        imp.confidence,
            "rationale":         imp.rationale,
        })

    # Sector rotation
    if result.sector_rotation and (result.sector_rotation.leaders or result.sector_rotation.laggards):
        sr = result.sector_rotation
        findings.append({
            "type":               "sector_rotation",
            "leaders":            sr.leaders,
            "laggards":           sr.laggards,
            "rotation_strength":  sr.rotation_strength,
        })

    # Knowledge-graph roll-up
    if result.knowledge_graph:
        findings.append({
            "type":            "knowledge_graph_summary",
            "n_entries":       len(result.knowledge_graph),
            "factor_kinds":    sorted({e.factor_kind for e in result.knowledge_graph}),
            "top_factors":     [e.factor for e in result.knowledge_graph[:5]],
        })

    # Composition
    findings.append({
        "type":               "composition",
        "n_commodities":      len(result.commodities),
        "n_currencies":       len(result.currencies),
        "n_bonds":            len(result.bonds),
        "n_active_impacts":   len(result.active_impacts),
        "n_kg_entries":       len(result.knowledge_graph),
    })

    # Headline
    regime_str = result.macro_regime.primary_regime if result.macro_regime else "unknown"
    vol_str = result.volatility.regime if result.volatility else "unknown"
    n_impacts = len(result.active_impacts)
    head = (f"regime={regime_str} · vol={vol_str} · active_impacts={n_impacts} · "
             + (f"macro_score={result.macro_regime.macro_score:+.2f}"
                if result.macro_regime else ""))
    narr = (head + ".\n\n"
             "AEGIS Macro & Intermarket Intelligence audit. Combines commodity moves, "
             "currency pressures, yield curve, VIX regime, and sector rotation into a "
             "single macro regime call. Emits an impact matrix + knowledge graph that "
             "downstream engines (Recommendation, Risk, Portfolio, Learning, AI Auditor) "
             "will consume from Sprint 8 onward.\n\n"
             "Does NOT approve or promote — every commodity impact, sector rotation call, "
             "and regime label is DESCRIPTIVE and requires operator interpretation. "
             "AI never trades on macro alone.")

    return AgentOutput(
        agent="macro_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={
            "primary_regime":    regime_str,
            "vol_regime":        vol_str,
            "n_active_impacts":  n_impacts,
            "macro_score":       result.macro_regime.macro_score if result.macro_regime else None,
        },
        citations=[
            "backend/macro_intel/engine.py",
            "configs/macro_intel_config.yaml",
            "backend/macro_intel/impact_matrix.py",
        ],
        confidence=0.85,
        caveats=[
            "impact matrix is deterministic template; extensible via config",
            "central-bank speeches/statements not ingested (deferred)",
            "descriptive only — never promotes",
        ],
        determinism="template",
    )
