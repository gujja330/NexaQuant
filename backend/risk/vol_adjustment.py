"""Volatility adjustment + VIX regime dampener."""
from __future__ import annotations


def vol_adjusted_size(raw_size: float, ticker_vol_annualised: float,
                        target_portfolio_vol: float) -> float:
    """Scale raw size by target_vol / ticker_vol (inverse-vol targeting).

    High-vol tickers get smaller sizes; low-vol tickers get larger sizes,
    such that each contributes roughly equal risk to the portfolio.
    """
    if ticker_vol_annualised is None or ticker_vol_annualised <= 0:
        return raw_size
    scale = target_portfolio_vol / ticker_vol_annualised
    # Bound to [0.25x, 4x] so we never leverage crazy or shrink to invisible
    scale = max(0.25, min(4.0, scale))
    return raw_size * scale


def vix_regime_dampener(regime: str, vix_level: float | None) -> float:
    """Multiplier applied to gross exposure based on volatility regime.

    Rules:
      bull / calm:          1.00  (full exposure)
      neutral / normal:     0.95
      elevated (VIX 25-35): 0.80
      stress (VIX > 35 OR regime == "stress"): 0.55
    """
    if regime == "stress":
        return 0.55
    if vix_level is not None:
        if vix_level > 35: return 0.55
        if vix_level > 25: return 0.80
        if vix_level > 18: return 0.95
    # Fall back to regime label
    if regime == "bear":     return 0.85
    if regime == "neutral":  return 0.95
    if regime == "bull":     return 1.00
    return 0.90  # unknown regime → slight dampener
