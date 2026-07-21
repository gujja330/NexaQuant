"""Per-ticker and per-sector exposure caps.

Applied AFTER Kelly + vol adjustment. If the raw sized position exceeds the
cap, we clip it and record the reason.
"""
from __future__ import annotations

from backend.risk.types import CapReason


def apply_per_ticker_cap(raw_weight: float, per_ticker_cap: float) -> tuple[float, bool]:
    """Clip a per-ticker weight to ±per_ticker_cap.

    Returns:
      (clipped_weight, was_capped)
    """
    if raw_weight > per_ticker_cap:
        return per_ticker_cap, True
    if raw_weight < -per_ticker_cap:
        return -per_ticker_cap, True
    return raw_weight, False


def apply_per_sector_cap(candidate_weight: float, sector: str,
                          current_sector_exposure: dict[str, float],
                          per_sector_cap: float) -> tuple[float, bool]:
    """Clip a candidate weight so the resulting sector total does not exceed cap.

    current_sector_exposure: {sector -> current signed exposure} BEFORE this position.
    Returns (clipped_weight, was_capped).
    """
    if not sector or sector.strip() == "":
        return candidate_weight, False
    current = current_sector_exposure.get(sector, 0.0)
    if candidate_weight >= 0:
        headroom = per_sector_cap - current
        if headroom <= 0:
            return 0.0, True
        if candidate_weight > headroom:
            return max(0.0, headroom), True
    else:
        # Short side — allow up to -per_sector_cap total
        headroom = -per_sector_cap - current
        if headroom >= 0:
            return 0.0, True
        if candidate_weight < headroom:
            return min(0.0, headroom), True
    return candidate_weight, False


def choose_cap_reason(kelly_hit: bool, ticker_hit: bool, sector_hit: bool,
                        vol_hit: bool, confidence_hit: bool,
                        disagreement_hit: bool, short_disabled: bool) -> CapReason:
    """Priority order: what actually bounded this position?"""
    if confidence_hit:   return CapReason.CONFIDENCE_GATE
    if disagreement_hit: return CapReason.DISAGREEMENT
    if short_disabled:   return CapReason.SHORT_DISABLED
    if sector_hit:       return CapReason.SECTOR_CAP
    if ticker_hit:       return CapReason.PER_TICKER_CAP
    if vol_hit:          return CapReason.VOL_CAP
    if kelly_hit:        return CapReason.KELLY
    return CapReason.NOT_CAPPED
