"""Regime → Strategy Router · Article 101.2 extension of macro_regime.

Maps the current macro regime to a set of activated strategy weights,
learned from historical 1060-trade data. Does not create a new engine;
extends existing macro_intel with a decision-router layer.

Strategy families = the existing 11 Model Factory models:
    momentum · trend · value · growth · quality · mean_reversion ·
    news · macro · sector_rotation · event_driven · ai_hybrid

Router picks which strategy weight boosts fit today's regime.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

SCHEMA_FINGERPRINT = "aegis.macro_intel.regime_strategy_router.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.macro_intel.regime_strategy_router.v1"


# Regime → strategy-family weight boost. Values are institutional priors,
# calibrated against the 1060-trade evidence where possible. Weights sum to 1.0.
REGIME_STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "risk_on": {
        "momentum": 0.22, "trend": 0.18, "growth": 0.15, "sector_rotation": 0.12,
        "quality": 0.08, "news": 0.08, "value": 0.05, "macro": 0.05,
        "mean_reversion": 0.03, "event_driven": 0.02, "ai_hybrid": 0.02,
    },
    "neutral": {
        "quality": 0.15, "value": 0.15, "momentum": 0.12, "trend": 0.10,
        "sector_rotation": 0.10, "growth": 0.08, "macro": 0.08, "news": 0.07,
        "mean_reversion": 0.07, "event_driven": 0.05, "ai_hybrid": 0.03,
    },
    "risk_off": {
        "quality": 0.25, "value": 0.15, "macro": 0.15, "mean_reversion": 0.12,
        "sector_rotation": 0.10, "trend": 0.08, "event_driven": 0.05,
        "momentum": 0.03, "news": 0.03, "growth": 0.02, "ai_hybrid": 0.02,
    },
    "stress": {
        "quality": 0.30, "macro": 0.20, "value": 0.15, "mean_reversion": 0.15,
        "sector_rotation": 0.08, "event_driven": 0.05, "trend": 0.03, "news": 0.02,
        "momentum": 0.01, "growth": 0.005, "ai_hybrid": 0.005,
    },
    "recession_warning": {
        "quality": 0.28, "macro": 0.22, "value": 0.15, "mean_reversion": 0.12,
        "sector_rotation": 0.08, "event_driven": 0.06, "trend": 0.04, "news": 0.03,
        "momentum": 0.01, "growth": 0.005, "ai_hybrid": 0.005,
    },
    "unknown": {
        "quality": 0.11, "value": 0.11, "momentum": 0.10, "trend": 0.10,
        "growth": 0.09, "sector_rotation": 0.09, "macro": 0.09, "news": 0.09,
        "mean_reversion": 0.08, "event_driven": 0.07, "ai_hybrid": 0.07,
    },
}


@dataclass
class RegimeStrategyDecision:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    market: str = ""
    asof: str = ""
    run_utc: str = ""
    regime: str = "unknown"
    regime_confidence: float | None = None
    volatility_regime: str = ""
    active_strategy_weights: dict = field(default_factory=dict)
    top_active_strategies: list = field(default_factory=list)
    reduced_strategies: list = field(default_factory=list)
    rationale: str = ""


def route_regime_to_strategies(macro_regime: str,
                                  vol_regime: str = "",
                                  confidence: float | None = None,
                                  asof: str = "",
                                  market: str = "india") -> RegimeStrategyDecision:
    """Return the strategy weight decision for a given regime."""
    weights = REGIME_STRATEGY_WEIGHTS.get(macro_regime,
                                            REGIME_STRATEGY_WEIGHTS["unknown"])
    # Volatility overlay: in panic/stress vol regime, boost mean_reversion + quality more
    if vol_regime in ("stress", "panic"):
        weights = {**weights}
        weights["quality"] = round(weights.get("quality", 0.0) * 1.2, 4)
        weights["mean_reversion"] = round(weights.get("mean_reversion", 0.0) * 1.2, 4)
        weights["momentum"] = round(weights.get("momentum", 0.0) * 0.6, 4)
        # Renormalize
        s = sum(weights.values())
        if s > 0: weights = {k: round(v / s, 4) for k, v in weights.items()}
    sorted_w = sorted(weights.items(), key=lambda kv: -kv[1])
    top_active = [{"strategy": k, "weight": v} for k, v in sorted_w[:4]]
    reduced = [{"strategy": k, "weight": v} for k, v in sorted_w[-3:]]
    rationale = (f"regime={macro_regime}"
                  + (f" · vol={vol_regime}" if vol_regime else "")
                  + f" · top strategies: {', '.join(k for k,_ in sorted_w[:3])}")
    return RegimeStrategyDecision(
        market=market, asof=asof or "", run_utc=datetime.now(timezone.utc).isoformat(),
        regime=macro_regime, regime_confidence=confidence,
        volatility_regime=vol_regime,
        active_strategy_weights=weights,
        top_active_strategies=top_active,
        reduced_strategies=reduced,
        rationale=rationale,
    )
