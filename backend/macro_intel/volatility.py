"""Volatility regime classification — VIX-based."""
from __future__ import annotations

from backend.macro_intel.types import VolatilityReading


def classify_volatility_regime(market: str, vix_level: float | None,
                                  chg_1m_pct: float | None = None) -> VolatilityReading:
    """Classify VIX level into calm / elevated / stress / panic."""
    if vix_level is None:
        return VolatilityReading(
            market=market, symbol="VIX", last=0.0,
            regime="unknown", chg_1m_pct=chg_1m_pct,
        )

    if vix_level < 15:      regime = "calm"
    elif vix_level < 22:    regime = "normal"
    elif vix_level < 30:    regime = "elevated"
    elif vix_level < 40:    regime = "stress"
    else:                     regime = "panic"

    return VolatilityReading(
        market=market, symbol="^VIX", last=float(vix_level),
        regime=regime, chg_1m_pct=chg_1m_pct,
    )
