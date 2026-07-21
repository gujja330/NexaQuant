"""Cash policy: apply regime-aware cash reserve."""
from __future__ import annotations


def compute_cash_reserve(regime: str, cash_reserve_min: float,
                          cash_reserve_stress: float) -> float:
    """Return the required cash reserve for the current regime.

    - stress regime:  cash_reserve_stress (e.g. 25%)
    - bear:           midpoint (min + stress) / 2
    - anything else:  cash_reserve_min
    """
    r = (regime or "").lower()
    if r == "stress":
        return max(cash_reserve_stress, cash_reserve_min)
    if r == "bear":
        # Halfway between min and stress
        return round((cash_reserve_min + cash_reserve_stress) / 2.0, 4)
    return cash_reserve_min
