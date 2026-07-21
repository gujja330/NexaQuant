"""Corporate action adjustments — dividends and splits.

Dividend day: cash += position_shares × dividend_amount
Split day:    shares × split_ratio; entry_price ÷= split_ratio
"""
from __future__ import annotations


def apply_corporate_actions(state: dict, corp_actions_today: list[dict]) -> dict:
    """Apply today's corp actions to running state in place. Returns state.

    state: {"cash": float, "positions": {ticker: {shares, entry_price, ...}, ...}}
    corp_actions_today: list of {"ticker": str, "dividend": float, "split_ratio": float}
    """
    positions = state.get("positions") or {}
    cash = float(state.get("cash", 0.0))

    for ca in corp_actions_today or []:
        ticker = str(ca.get("ticker") or "")
        div = float(ca.get("dividend") or 0.0)
        sp  = float(ca.get("split_ratio") or 0.0)
        pos = positions.get(ticker)
        if not pos: continue

        if div > 0:
            # Cash dividend to the position holder
            cash += float(pos.get("shares", 0.0)) * div

        if sp > 0 and sp != 1.0:
            pos["shares"] = float(pos.get("shares", 0.0)) * sp
            entry = pos.get("entry_price")
            if entry is not None and entry > 0:
                pos["entry_price"] = float(entry) / sp

    state["cash"] = cash
    state["positions"] = positions
    return state
