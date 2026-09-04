"""Fundamentals · Layer 3 · Change / Momentum (4 signals)

Analyst Revision Momentum · Guidance Revision · Earnings Surprise · Insider F4.
"""
from __future__ import annotations

from typing import Optional


def analyst_rev_momentum(fin: dict) -> Optional[float]:
    """(Consensus_EPS_now - Consensus_EPS_3mo_ago) / |Consensus_EPS_3mo_ago|.

    Direction-of-expectations signal. Positive = upgrades outweighing downgrades.
    """
    for k in ("consensus_eps_now", "consensus_eps_3mo_ago"):
        if k not in fin or fin[k] is None:
            return None
    try:
        prev = float(fin["consensus_eps_3mo_ago"])
        if prev == 0:
            return None
        now = float(fin["consensus_eps_now"])
        return round((now - prev) / abs(prev), 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def guidance_revision(fin: dict) -> Optional[float]:
    """Direction of most-recent management guidance vs prior · {-1, 0, +1}.

    Providers usually return categorical · we map:
      RAISED / ABOVE   →  +1
      MAINTAINED / IN  →   0
      LOWERED / BELOW  →  -1
    Missing → None.
    """
    v = fin.get("guidance_direction")
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("RAISED", "ABOVE", "BEAT", "UP", "+1", "1"): return 1.0
    if s in ("LOWERED", "BELOW", "MISS", "DOWN", "-1"): return -1.0
    if s in ("MAINTAINED", "IN_LINE", "INLINE", "FLAT", "0"): return 0.0
    return None


def earnings_surprise(fin: dict) -> Optional[float]:
    """(Actual_EPS - Consensus_EPS) / |Consensus_EPS| for most recent report."""
    for k in ("actual_eps", "consensus_eps"):
        if k not in fin or fin[k] is None:
            return None
    try:
        c = float(fin["consensus_eps"])
        if c == 0:
            return None
        return round((float(fin["actual_eps"]) - c) / abs(c), 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def insider_f4_signal(fin: dict) -> Optional[float]:
    """Net insider $ over trailing 90d divided by market cap.

    Uses Form-4 (USA) / SAST disclosures (India) net buy-sell $ from the
    provider. Positive = net insider buying.
    """
    for k in ("insider_net_dollars_90d", "market_cap"):
        if k not in fin or fin[k] is None:
            return None
    try:
        mc = float(fin["market_cap"])
        if mc <= 0:
            return None
        return round(float(fin["insider_net_dollars_90d"]) / mc, 8)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def revenue_growth_yoy(fin: dict) -> Optional[float]:
    """Year-over-year revenue growth · PIT-safe · CEO 2026-09-05 F05 unblock.

    Requires provider to supply both current-year and prior-year revenue as
    reported at or before the asof date. Provider MUST NOT include the most
    recent unreported fiscal year · that is the PIT-safety contract.

    fin keys:
      revenue_current_annual   · most recent reported annual revenue as of asof
      revenue_prior_annual     · the fiscal year immediately preceding
      revenue_report_date      · the reporting date of the current annual value
                                  (used by provider to enforce ≤ asof)

    Returns · (current - prior) / |prior| · positive = growth. None if either
    revenue is missing, prior <= 0, or provider flagged post-asof leakage.
    """
    for k in ("revenue_current_annual", "revenue_prior_annual"):
        if k not in fin or fin[k] is None:
            return None
    # PIT safety guard · caller must have already verified report_date <= asof
    # (kept in provider · signalled here by absence of revenue_pit_violated flag).
    if fin.get("revenue_pit_violated"):
        return None
    try:
        prev = float(fin["revenue_prior_annual"])
        if prev <= 0: return None
        cur = float(fin["revenue_current_annual"])
        return round((cur - prev) / abs(prev), 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def inst_13f_change(fin: dict) -> Optional[float]:
    """13F institutional-holdings quarter-over-quarter change.

    USA: aggregate 13F institutional shares held this-quarter vs prior-quarter,
         as a fraction of prior-quarter total. Positive = accumulation.
    India: fall back to SAST 5%+ disclosure changes (proxy).

    fin keys:
      inst_shares_qtr:  total institutional shares this reporting quarter
      inst_shares_prev_qtr: same, prior quarter
    """
    for k in ("inst_shares_qtr", "inst_shares_prev_qtr"):
        if k not in fin or fin[k] is None:
            return None
    try:
        prev = float(fin["inst_shares_prev_qtr"])
        if prev <= 0: return None
        return round((float(fin["inst_shares_qtr"]) - prev) / prev, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


LAYER3_FUNCTIONS = {
    "analyst_rev_momentum": analyst_rev_momentum,
    "guidance_rev":         guidance_revision,
    "earnings_surprise":    earnings_surprise,
    "insider_f4_signal":    insider_f4_signal,
    "inst_13f_change":      inst_13f_change,
    "revenue_growth_yoy":   revenue_growth_yoy,   # F05 unblock · CEO 2026-09-05
}
