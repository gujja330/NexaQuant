"""Slippage model — linear-impact + vol-adjusted.

slippage_bps = MIN_SLIPPAGE_BPS
             + LIQUIDITY_IMPACT × (order_size / adv_20d)
             + VOL_IMPACT × vol_20d_annualised

Signed against the trade direction (long buys pay UP, shorts pay DOWN).
"""
from __future__ import annotations


def compute_slippage_bps(order_size_shares: float, adv_20d_shares: float,
                            vol_20d_annualised: float,
                            min_slippage_bps: float,
                            liquidity_impact_bps: float,
                            vol_impact_bps: float,
                            direction: int = +1) -> float:
    """Return signed slippage in bps (positive = adverse to the trader).

    direction: +1 for BUY (fill above mid), -1 for SELL (fill below mid).
    """
    if adv_20d_shares is None or adv_20d_shares <= 0:
        participation = 0.0
    else:
        participation = max(0.0, min(1.0, order_size_shares / adv_20d_shares))
    vol = max(0.0, vol_20d_annualised or 0.0)
    slip_bps = (min_slippage_bps
                + liquidity_impact_bps * participation
                + vol_impact_bps * vol)
    return float(direction) * float(slip_bps)
