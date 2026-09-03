"""Fundamentals · Layer 2 · Value (4 signals)

FCF Yield · EV/EBITDA · Total Shareholder Yield · Sector-relative Value Rank.
"""
from __future__ import annotations

from typing import Optional


def fcf_yield(fin: dict) -> Optional[float]:
    """Free_Cash_Flow_ttm / Market_Cap · higher = cheaper."""
    for k in ("fcf_ttm", "market_cap"):
        if k not in fin or fin[k] is None:
            return None
    try:
        mc = float(fin["market_cap"])
        if mc <= 0:
            return None
        return round(float(fin["fcf_ttm"]) / mc, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def ev_ebitda(fin: dict) -> Optional[float]:
    """Enterprise_Value / EBITDA_ttm · lower = cheaper · negative EBITDA → None."""
    for k in ("enterprise_value", "ebitda_ttm"):
        if k not in fin or fin[k] is None:
            return None
    try:
        eb = float(fin["ebitda_ttm"])
        if eb <= 0:
            return None
        return round(float(fin["enterprise_value"]) / eb, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def total_shareholder_yield(fin: dict) -> Optional[float]:
    """(Dividends_paid + Buybacks - Share_Issuance) / Market_Cap over TTM."""
    for k in ("dividends_ttm", "buybacks_ttm", "issuance_ttm", "market_cap"):
        if k not in fin or fin[k] is None:
            return None
    try:
        mc = float(fin["market_cap"])
        if mc <= 0:
            return None
        tsy = (
            float(fin["dividends_ttm"])
            + float(fin["buybacks_ttm"])
            - float(fin["issuance_ttm"])
        ) / mc
        return round(tsy, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def sector_rel_value_rank(fcf_y: Optional[float], ev_eb: Optional[float],
                          tsy: Optional[float],
                          sector_cohort: list[dict]) -> Optional[float]:
    """Composite value-percentile rank within sector cohort on asof.

    Combines FCF yield (+direction), EV/EBITDA (-direction), TSY (+direction)
    as equal-weighted ranks · returns [0, 1] percentile · 1.0 = cheapest.

    sector_cohort · list of {ticker, fcf_yield, ev_ebitda, total_shareholder_yield}
    for the same sector on the same asof.
    """
    if fcf_y is None and ev_eb is None and tsy is None:
        return None
    if not sector_cohort or len(sector_cohort) < 3:
        # Need >=3 peers to make a meaningful percentile
        return None

    def _rank_asc(vals: list[float], v: float) -> float:
        vs = sorted(vals)
        n = len(vs)
        below = sum(1 for x in vs if x < v)
        return below / (n - 1) if n > 1 else 0.5

    parts: list[float] = []
    # FCF yield · higher better
    fcfs = [x["fcf_yield"] for x in sector_cohort
            if x.get("fcf_yield") is not None]
    if fcf_y is not None and fcfs:
        parts.append(_rank_asc(fcfs, fcf_y))
    # EV/EBITDA · lower better · invert
    evs = [x["ev_ebitda"] for x in sector_cohort
           if x.get("ev_ebitda") is not None and x.get("ev_ebitda") > 0]
    if ev_eb is not None and ev_eb > 0 and evs:
        parts.append(1.0 - _rank_asc(evs, ev_eb))
    # TSY · higher better
    tsys = [x["total_shareholder_yield"] for x in sector_cohort
            if x.get("total_shareholder_yield") is not None]
    if tsy is not None and tsys:
        parts.append(_rank_asc(tsys, tsy))

    if not parts:
        return None
    return round(sum(parts) / len(parts), 4)


LAYER2_FUNCTIONS = {
    "fcf_yield":              fcf_yield,
    "ev_ebitda":              ev_ebitda,
    "total_shareholder_yield":total_shareholder_yield,
    # sector_rel_value_rank is applied post-cohort · builder handles it
}
