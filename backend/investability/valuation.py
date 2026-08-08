"""Valuation sub-engine · 8% weight of Investability Score.

Purpose: separate "quality company at bad price" from "poor quality".
Fixes the HDFCBANK-false-REJECT case where Wave 1 rejected on weak
momentum ignoring that HDFCBANK is cheap on valuation basis.

Signals (yfinance ticker.info derivable · no new data source):
    Trailing P/E vs sector norm (yfinance sector defaults)
    Forward P/E
    P/B (Price to Book)
    PEG (P/E to Growth ratio · < 1.5 = reasonable)
    EV/EBITDA (< 15 = reasonable for most sectors)
    Earnings yield vs 10-yr bond yield (India: ~7% · US: ~4.5%)
    Dividend yield (positive = distributive shareholder policy)
    Price to Sales

Returns 0-100 score.

Higher score = better valuation (cheaper relative to fundamentals).
"""
from __future__ import annotations


# Bond yield assumptions for earnings-yield check
BOND_YIELD = {"india": 7.0, "usa": 4.5}


def score(info: dict, market: str = "india") -> tuple[float, dict]:
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

    # P/E not extreme (positive · below 40 is investable range)
    pe = info.get("trailingPE")
    check("pe_investable_range", pe, lambda v: 0 < v < 40, weight=2.0)

    # Forward P/E better than trailing (growth expected)
    fwd_pe = info.get("forwardPE")
    if pe and fwd_pe and pe > 0 and fwd_pe > 0:
        check("forward_pe_improving", fwd_pe, lambda v: v <= pe, weight=1.5)

    # PEG ≤ 1.5 = reasonable growth-adjusted
    peg = info.get("pegRatio") or info.get("trailingPegRatio")
    check("peg_reasonable", peg, lambda v: 0 < v <= 1.5, weight=2.0)

    # P/B < 5 (below 3 is even better · sector-dependent · this is generous)
    pb = info.get("priceToBook")
    check("pb_reasonable", pb, lambda v: 0 < v < 5, weight=1.5)

    # EV/EBITDA · < 15 = investable
    ev_ebitda = info.get("enterpriseToEbitda")
    check("ev_ebitda_reasonable", ev_ebitda, lambda v: 0 < v < 15, weight=1.5)

    # Price/Sales · < 5 = reasonable
    ps = info.get("priceToSalesTrailing12Months")
    check("ps_reasonable", ps, lambda v: 0 < v < 5, weight=1.0)

    # Earnings yield > bond yield (yfinance earnings/price · convert PE → E/P)
    if pe and pe > 0:
        earnings_yield_pct = 100.0 / pe
        bond_y = BOND_YIELD.get(market.lower(), 6.0)
        check("earnings_yield_beats_bond", earnings_yield_pct,
                  lambda v: v > bond_y, weight=1.5)

    # Dividend yield present (shareholder-friendly capital allocation)
    div_yield = info.get("dividendYield")
    check("pays_dividend", div_yield, lambda v: v is not None and v > 0, weight=0.5)

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "valuation.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
    }
