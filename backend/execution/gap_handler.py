"""Overnight gap handling — mark stop-loss / take-profit hits at OPEN."""
from __future__ import annotations


def gap_stop_out(prev_close: float, today_open: float,
                    is_long: bool, stop_loss_pct: float | None,
                    gap_threshold_pct: float = 0.03) -> tuple[bool, float | None]:
    """Detect an overnight gap that hits the stop-loss at open.

    Args:
      prev_close:       yesterday's close
      today_open:       today's open
      is_long:          True if the position is long
      stop_loss_pct:    e.g. -0.08 for -8% stop
      gap_threshold_pct: only classify as a gap-out if |return| > this

    Returns:
      (hit_stop, effective_price)
    """
    if prev_close <= 0 or stop_loss_pct is None:
        return False, None
    ret = today_open / prev_close - 1.0
    if abs(ret) < gap_threshold_pct:
        return False, None
    if is_long and ret <= stop_loss_pct:
        # Gap-down through stop → mark at OPEN
        return True, float(today_open)
    if (not is_long) and ret >= abs(stop_loss_pct):
        return True, float(today_open)
    return False, None
