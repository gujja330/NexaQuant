"""Sizing math — Kelly-fractional + confidence-tier + volatility scaling.

All deterministic, no random state.
"""
from __future__ import annotations


def kelly_fractional_size(edge: float, vol_annualised: float,
                             max_kelly_fraction: float = 0.25) -> float:
    """Kelly-fractional sizing.

    Kelly (unrestricted) = edge / variance  (for a normal-return bet).
    We use fractional Kelly (typically 25%) to reduce sensitivity to edge
    estimation error and to make drawdowns tolerable.

    Args:
      edge:              expected excess return (edge over risk-free).
                         For our system: ensemble_score × confidence.
      vol_annualised:    annualised volatility. Non-zero.
      max_kelly_fraction: cap on the fraction of full-Kelly to bet.

    Returns:
      A fractional position size, sign-preserving. Bounded by ± max_kelly_fraction.
    """
    if vol_annualised is None or vol_annualised <= 0:
        return 0.0
    variance = vol_annualised ** 2
    raw = edge / variance
    # Clamp to ± max_kelly_fraction
    return max(-max_kelly_fraction, min(max_kelly_fraction, raw))


def confidence_tier_multiplier(action: str, tier_mult: dict) -> float:
    """Return the confidence-tier multiplier for a given action.

    tier_mult example (from RiskBudget.confidence_tier_mult):
      {"STRONG_BUY": 1.0, "BUY": 0.6, "HOLD": 0.0, "SELL": -0.6, "STRONG_SELL": -1.0}
    """
    return float(tier_mult.get(action, 0.0))
