"""Fundamental features from CanonicalFundamentals rows."""
from __future__ import annotations

import math
from datetime import date

from backend.canonical.schemas import CanonicalDataset


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    funds = canon.get("fundamentals")
    if not funds or not funds.rows:
        return out
    for f in funds.rows:
        if f.symbol not in universe:
            continue
        cap_log = None
        if f.market_cap and f.market_cap > 0:
            cap_log = round(math.log10(f.market_cap), 4)
        out[f.symbol] = {
            "fund_roe":              f.roe,
            "fund_debt_to_equity":   f.debt_to_equity,
            "fund_profit_margin":    f.profit_margin,
            "fund_earnings_growth":  f.earnings_growth,
            "fund_trailing_pe":      f.trailing_pe,
            "fund_price_to_book":    f.price_to_book,
            "fund_quality_score":    f.quality_score,
            "fund_market_cap_log":   cap_log,
        }
    return out
