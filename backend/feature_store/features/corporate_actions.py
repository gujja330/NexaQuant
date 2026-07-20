"""Corporate action features from CanonicalCorporateAction rows."""
from __future__ import annotations

from datetime import date

from backend.canonical.schemas import CanonicalDataset


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {t: {} for t in universe}
    ca = canon.get("corporate_action")
    if not ca or not ca.rows:
        return out

    # Sort per ticker chronologically
    by_sym: dict[str, list] = {}
    for r in ca.rows:
        if r.symbol not in universe: continue
        by_sym.setdefault(r.symbol, []).append(r)

    for sym, rows in by_sym.items():
        rows.sort(key=lambda r: r.action_date)
        last_div = next((r for r in reversed(rows) if r.dividend > 0), None)
        last_sp  = next((r for r in reversed(rows) if r.split_ratio > 0), None)
        if last_div is not None:
            out[sym]["ca_days_since_last_dividend"] = (asof - last_div.action_date).days
            out[sym]["ca_last_dividend_amount"]     = round(last_div.dividend, 4)
        if last_sp is not None:
            out[sym]["ca_days_since_last_split"] = (asof - last_sp.action_date).days
            out[sym]["ca_last_split_ratio"]      = round(last_sp.split_ratio, 4)
    return out
