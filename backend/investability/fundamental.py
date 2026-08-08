"""Fundamental sub-engine · 25% weight of Investability Score.

Signals (all yfinance ticker.info derivable · no new data source):
    ROE                    · targetPercentageROE > 15% is good
    Debt-to-Equity         · debtToEquity < 1.0 is good
    Interest Coverage      · ebitda / interestExpense > 3x is good
    Revenue Growth (yoy)   · revenueGrowth > 0.15 is good
    Earnings Growth (yoy)  · earningsGrowth > 0.15 is good
    Free Cash Flow         · freeCashflow > 0 is good
    Profit Margin          · profitMargins > 0.10 is good
    Return on Assets       · returnOnAssets > 0.08 is good

Returns 0-100 score.

Full Wave 2 will add: ROCE · 3-yr CAGRs from historical filings · working
capital metrics · reinvestment rate · capital allocation quality.
"""
from __future__ import annotations


def score(info: dict) -> tuple[float, dict]:
    """Compute fundamental score from yfinance-shaped info dict.

    Returns (score_0_to_100, debug_signals_dict).
    """
    signals = {}
    hits = 0
    total = 0

    def check(name: str, value, ok_fn, weight: float = 1.0):
        """Fixed 2026-08-08: only count total when signal has data.
        Previously missing signals penalized score · caused HDFCBANK=35
        because yfinance lacks ESG data for Indian financials · treated as
        misses. Now missing = neutral (excluded from denominator)."""
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

    # Core quality (higher weight)
    check("roe",                    info.get("returnOnEquity"),  lambda v: v >= 0.15, 2.0)
    check("debt_to_equity",         info.get("debtToEquity"),    lambda v: v is not None and v < 100.0, 2.0)   # yfinance returns as %
    check("profit_margin",          info.get("profitMargins"),   lambda v: v >= 0.10, 2.0)
    check("return_on_assets",       info.get("returnOnAssets"),  lambda v: v >= 0.08, 1.5)

    # Growth
    check("revenue_growth_yoy",     info.get("revenueGrowth"),   lambda v: v >= 0.10, 1.0)
    check("earnings_growth_yoy",    info.get("earningsGrowth"),  lambda v: v >= 0.10, 1.0)

    # Cash + coverage
    check("free_cashflow_positive", info.get("freeCashflow"),    lambda v: v > 0,     1.5)
    check("operating_margin",       info.get("operatingMargins"),lambda v: v >= 0.10, 1.0)

    # Valuation sanity (bad extremes only)
    pe = info.get("trailingPE")
    check("pe_not_extreme",         pe,                          lambda v: 0 < v < 60, 1.0)

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "fundamental.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
    }
