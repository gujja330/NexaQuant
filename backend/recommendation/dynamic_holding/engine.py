"""Dynamic Holding Engine · Constitution-compliant.

Given a position + market state, return a suggested holding period in days.
Never returns a static "30" or "60"; every output is a composite of the
11 factors listed in the operator spec.

Bounded to [3, 180] trading days. Deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

SCHEMA_FINGERPRINT = "aegis.dynamic_holding.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.dynamic_holding.v1"

MIN_HOLDING_DAYS = 3
MAX_HOLDING_DAYS = 180
BASE_HOLDING_DAYS = 21  # baseline · adjusted by 11-factor composite

# Regime multipliers (extend/shorten hold based on macro regime)
REGIME_MULT = {
    "risk_on":           1.10,
    "neutral":           1.00,
    "risk_off":          0.60,
    "stress":            0.40,
    "recession_warning": 0.50,
    "unknown":           0.85,
}


@dataclass(frozen=True)
class HoldingDecision:
    ticker: str
    holding_days: int
    base_days: int
    regime_multiplier: float
    confidence_factor: float
    upside_factor: float
    sector_factor: float
    rotation_factor: float
    risk_factor: float
    volatility_factor: float
    liquidity_factor: float
    portfolio_overlap_factor: float
    opportunity_cost_factor: float
    benchmark_alpha_factor: float
    reason: str
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _confidence_decay_factor(current_confidence: float, confidence_at_entry: float) -> float:
    """Lower current confidence relative to entry -> shorten hold."""
    entry = _clip(confidence_at_entry, 0.01, 1.0)
    curr = _clip(current_confidence, 0.0, 1.0)
    ratio = curr / entry  # 1.0 = unchanged · >1 improving · <1 decaying
    return _clip(ratio, 0.5, 1.4)


def _upside_factor(upside_remaining_pct: float) -> float:
    """More upside remaining -> longer hold."""
    x = _clip(upside_remaining_pct, -30.0, 30.0) / 20.0  # 20% upside -> +1.0
    return _clip(1.0 + 0.5 * x, 0.5, 1.5)


def _sector_factor(sector_strength: float) -> float:
    """Stronger sector -> longer hold."""
    return _clip(1.0 + 0.3 * (_clip(sector_strength, -20.0, 20.0) / 20.0), 0.7, 1.3)


def _rotation_factor(rotation_score: float) -> float:
    """Higher rotation score (better candidate elsewhere) -> shorter hold."""
    r = _clip(rotation_score, -1.0, 1.0)
    return _clip(1.0 - 0.5 * r, 0.5, 1.5)


def _risk_factor(risk_score: float) -> float:
    """Higher risk -> shorter hold."""
    return _clip(1.0 - 0.4 * _clip(risk_score, 0.0, 1.0), 0.6, 1.0)


def _volatility_factor(annualized_vol: float) -> float:
    """Higher vol -> shorter hold (mean-reverting horizon adaptation)."""
    v = _clip(annualized_vol, 0.05, 1.5)
    # Baseline 0.25 (25% annualized) -> 1.0
    return _clip(0.25 / v, 0.5, 1.4)


def _liquidity_factor(liquidity_ratio: float) -> float:
    """Higher liquidity -> longer hold OK · low liquidity -> shorten."""
    return _clip(0.7 + 0.5 * _clip(liquidity_ratio, 0.0, 2.0), 0.7, 1.4)


def _portfolio_overlap_factor(overlap_pct: float) -> float:
    """More overlap with existing portfolio -> shorten (redundancy)."""
    return _clip(1.0 - 0.4 * _clip(overlap_pct, 0.0, 1.0), 0.6, 1.0)


def _opp_cost_factor(opp_cost_edge: float) -> float:
    """Higher opportunity cost of holding (better alternatives) -> shorten."""
    return _clip(1.0 - 0.5 * _clip(opp_cost_edge, 0.0, 1.0), 0.5, 1.0)


def _bench_alpha_factor(expected_alpha_pct: float) -> float:
    """Higher expected benchmark alpha -> longer hold."""
    return _clip(1.0 + 0.4 * (_clip(expected_alpha_pct, -20.0, 20.0) / 20.0), 0.6, 1.4)


class DynamicHoldingEngine:
    """Deterministic Dynamic Holding Engine."""

    def compute(self,
                 ticker: str,
                 *,
                 current_confidence: float,
                 confidence_at_entry: float,
                 upside_remaining_pct: float,
                 sector_strength: float,
                 macro_regime: str,
                 rotation_score: float,
                 risk_score: float,
                 annualized_vol: float,
                 liquidity_ratio: float,
                 portfolio_overlap_pct: float,
                 opp_cost_edge: float,
                 expected_benchmark_alpha_pct: float) -> HoldingDecision:
        regime_mult = REGIME_MULT.get(macro_regime, REGIME_MULT["unknown"])
        conf = _confidence_decay_factor(current_confidence, confidence_at_entry)
        upside = _upside_factor(upside_remaining_pct)
        sector = _sector_factor(sector_strength)
        rotation = _rotation_factor(rotation_score)
        risk = _risk_factor(risk_score)
        vol = _volatility_factor(annualized_vol)
        liquidity = _liquidity_factor(liquidity_ratio)
        overlap = _portfolio_overlap_factor(portfolio_overlap_pct)
        opp = _opp_cost_factor(opp_cost_edge)
        bench = _bench_alpha_factor(expected_benchmark_alpha_pct)

        composite = (regime_mult * conf * upside * sector * rotation * risk
                     * vol * liquidity * overlap * opp * bench)
        days = int(round(BASE_HOLDING_DAYS * composite))
        days = int(_clip(days, MIN_HOLDING_DAYS, MAX_HOLDING_DAYS))

        drivers = []
        if conf < 0.85: drivers.append(f"confidence decay ({conf:.2f}x)")
        if upside > 1.15: drivers.append(f"upside remains ({upside:.2f}x)")
        if rotation < 0.85: drivers.append(f"rotation-away pressure ({rotation:.2f}x)")
        if risk < 0.85: drivers.append(f"risk trim ({risk:.2f}x)")
        if regime_mult < 0.85: drivers.append(f"regime {macro_regime} ({regime_mult:.2f}x)")
        reason = f"dynamic holding {days}d = base {BASE_HOLDING_DAYS} × composite {composite:.3f}"
        if drivers:
            reason += " · drivers: " + " · ".join(drivers)

        return HoldingDecision(
            ticker=ticker, holding_days=days, base_days=BASE_HOLDING_DAYS,
            regime_multiplier=regime_mult,
            confidence_factor=round(conf, 4),
            upside_factor=round(upside, 4),
            sector_factor=round(sector, 4),
            rotation_factor=round(rotation, 4),
            risk_factor=round(risk, 4),
            volatility_factor=round(vol, 4),
            liquidity_factor=round(liquidity, 4),
            portfolio_overlap_factor=round(overlap, 4),
            opportunity_cost_factor=round(opp, 4),
            benchmark_alpha_factor=round(bench, 4),
            reason=reason,
        )


def compute_holding_days(ticker: str, **kwargs) -> dict:
    return asdict(DynamicHoldingEngine().compute(ticker, **kwargs))
