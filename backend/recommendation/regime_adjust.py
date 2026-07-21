"""Regime Adjustment — reflect market regime in confidence and holding period.

- Bull regime → BUY signals get full trust; SELL signals dampened
- Neutral    → slight dampening on both
- Bear       → SELL signals get full trust; BUY signals dampened
- Stress    → BUY signals heavily dampened; suggest shorter holds

Multipliers are deterministic constants — no random state.
"""
from __future__ import annotations


# regime → (buy_mult, sell_mult, holding_period_days_baseline)
_MULTIPLIERS = {
    "bull":    (1.00, 0.85,  90),
    "neutral": (0.95, 0.95,  60),
    "bear":    (0.85, 1.00,  45),
    "stress":  (0.65, 1.00,  30),
    "unknown": (0.85, 0.85,  60),
}


def apply_regime_adjustment(regime: str, ensemble_score: float,
                              confidence: float) -> tuple[float, int]:
    """Return (regime_adjusted_confidence, suggested_holding_days)."""
    key = (regime or "unknown").lower()
    buy_m, sell_m, hold_days = _MULTIPLIERS.get(key, _MULTIPLIERS["unknown"])
    mult = buy_m if ensemble_score >= 0 else sell_m
    return round(max(0.0, min(1.0, confidence * mult)), 4), int(hold_days)
