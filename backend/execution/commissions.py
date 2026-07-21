"""Commissions — flat bps per market. Sprint 7 baseline."""
from __future__ import annotations


def commission_bps(commission_bps_config: float, notional: float) -> tuple[float, float]:
    """Return (bps, amount_in_currency)."""
    if notional <= 0:
        return 0.0, 0.0
    amt = notional * (commission_bps_config / 10_000.0)
    return float(commission_bps_config), float(amt)
