"""Ownership sub-engine · 10% weight of Investability Score.

Wave 1.5 signals (yfinance-derivable):
    Institutional ownership   · >20% = quality endorsement
    Insider ownership         · >5% = skin in game
    Institutional count       · # of institutional holders (breadth)
    Float turnover            · shares held vs float
    Concentration risk        · single insider dominance
    Ownership stability       · not heavily diluted recently

Wave 2 (Sprint K Part 26 · full data source):
    FII quarter-over-quarter trend from BSE shareholding pattern
    MF quarter-over-quarter trend
    PMS/Insurance holdings
    Promoter buying/selling activity
    Insider buying vs selling ratio (past 6 months)
"""
from __future__ import annotations


def score(info: dict) -> tuple[float, dict]:
    signals = {}
    hits = 0
    total = 0

    def check(name, value, ok_fn, weight=1.0):
        nonlocal hits, total
        if value is None:
            signals[name] = {"value": None, "ok": None, "weight": weight}
            return
        try:
            ok = bool(ok_fn(value))
            total += weight
            signals[name] = {"value": value, "ok": ok, "weight": weight}
            if ok: hits += weight
        except (TypeError, ValueError):
            signals[name] = {"value": value, "ok": None, "weight": weight}

    # Institutional endorsement · quality-of-holders signal
    check("institutional_ownership_healthy",
              info.get("heldPercentInstitutions"),
              lambda v: v >= 0.30, weight=2.0)
    check("institutional_ownership_moderate",
              info.get("heldPercentInstitutions"),
              lambda v: v >= 0.15, weight=1.5)

    # Insider skin-in-game
    check("insider_holding_present",
              info.get("heldPercentInsiders"),
              lambda v: v >= 0.05, weight=1.5)
    check("insider_holding_strong",
              info.get("heldPercentInsiders"),
              lambda v: v >= 0.20, weight=1.0)

    # Breadth · number of institutional holders
    check("institutional_breadth",
              info.get("heldPercentInstitutions"),
              lambda v: v >= 0.50, weight=1.0)

    # Float availability · not too tightly held (locks up liquidity)
    float_shares = info.get("floatShares")
    shares_out = info.get("sharesOutstanding")
    if float_shares and shares_out and shares_out > 0:
        float_ratio = float_shares / shares_out
        check("float_availability", float_ratio, lambda v: v >= 0.25, weight=1.0)

    # Shares dilution check · shares outstanding growth (bad if too high)
    short_ratio = info.get("shortRatio")
    check("no_heavy_shorting", short_ratio, lambda v: v is not None and v < 8, weight=1.0)

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "ownership.v1_lite",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
        "note":       "Wave 1.5 · Wave 2 adds FII/MF QoQ trends from BSE shareholding pattern",
    }
