"""Composite macro regime classifier.

Combines: rates (bond yields) + commodities + currency + VIX → risk-on/risk-off
+ inflationary/deflationary + commodity-bull/bear + recession warning.

Deterministic. Uses simple rule combinations. Sprint 9 AI Auditor may propose
alternative weightings via promotion gate.
"""
from __future__ import annotations

from datetime import date

from backend.macro_intel.types import (
    CommodityReading, CurrencyReading, BondReading,
    VolatilityReading, MacroRegimeReading, RegimeLabel,
)


def classify_macro_regime(market: str, asof: date,
                             commodities: list[CommodityReading],
                             currencies: list[CurrencyReading],
                             bonds: list[BondReading],
                             volatility: VolatilityReading | None,
                             yield_curve_inversion: bool = False) -> MacroRegimeReading:
    """Return a MacroRegimeReading with primary + secondary label + composite score."""
    evidence: dict = {}
    score = 0.0

    # ── Volatility contribution ──────────────────────────────
    vol_regime = volatility.regime if volatility else "unknown"
    evidence["vol_regime"] = vol_regime
    if vol_regime == "calm":       score += 0.4
    elif vol_regime == "normal":   score += 0.1
    elif vol_regime == "elevated": score -= 0.2
    elif vol_regime == "stress":   score -= 0.5
    elif vol_regime == "panic":    score -= 0.8

    # ── Commodity contribution ──────────────────────────────
    oil_1w = next((c.chg_1w_pct for c in commodities if c.symbol in ("CL=F", "BZ=F")), None)
    gold_1w = next((c.chg_1w_pct for c in commodities if c.symbol == "GC=F"), None)
    evidence["oil_1w_pct"]  = oil_1w
    evidence["gold_1w_pct"] = gold_1w

    commodity_bull = False; commodity_bear = False
    if oil_1w is not None:
        if oil_1w > 5:     score -= 0.2; commodity_bull = True   # oil spike = inflation → risk-off
        elif oil_1w < -5:  score += 0.1; commodity_bear = True

    # Gold rally + risk-off often coincide
    if gold_1w is not None and gold_1w > 3:
        score -= 0.15
        evidence["gold_flight_to_safety"] = True

    # ── Currency contribution ───────────────────────────────
    dxy_1w = next((c.chg_1w_pct for c in currencies if c.symbol == "UUP"), None)
    evidence["usd_1w_pct"] = dxy_1w
    if dxy_1w is not None:
        if dxy_1w > 1.5:  score -= 0.2       # strong dollar = risk-off for equities
        elif dxy_1w < -1.5: score += 0.15

    # ── Yield curve inversion ───────────────────────────────
    evidence["yield_curve_inversion"] = yield_curve_inversion
    if yield_curve_inversion:
        score -= 0.3

    # ── Interest rate direction ─────────────────────────────
    ten_1m = next((b.chg_1m_bps for b in bonds if b.symbol == "^TNX"), None)
    evidence["ten_year_1m_bps"] = ten_1m
    if ten_1m is not None:
        if ten_1m > 25:   score -= 0.15      # rates rising fast = risk-off
        elif ten_1m < -25: score += 0.15

    # Clamp
    score = max(-1.0, min(1.0, score))

    # ── Primary label ───────────────────────────────────────
    if score >= 0.30:                    primary = RegimeLabel.RISK_ON
    elif score <= -0.30:                 primary = RegimeLabel.RISK_OFF
    elif yield_curve_inversion:          primary = RegimeLabel.RECESSION_WARNING
    else:                                 primary = RegimeLabel.UNKNOWN

    # ── Secondary label ─────────────────────────────────────
    secondary = None
    if commodity_bull and (oil_1w or 0) > 5:
        secondary = RegimeLabel.INFLATIONARY.value
    elif commodity_bear:
        secondary = RegimeLabel.DEFLATIONARY.value
    elif commodity_bull:
        secondary = RegimeLabel.COMMODITY_BULL.value

    # ── Confidence heuristic ────────────────────────────────
    n_signals = sum(1 for v in [oil_1w, gold_1w, dxy_1w, ten_1m, vol_regime] if v is not None and v != "unknown")
    confidence = min(1.0, 0.4 + 0.1 * n_signals)

    return MacroRegimeReading(
        market=market, asof=asof,
        primary_regime=primary.value,
        secondary_regime=secondary,
        confidence=round(confidence, 3),
        evidence=evidence,
        macro_score=round(score, 3),
    )
