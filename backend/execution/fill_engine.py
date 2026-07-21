"""Fill engine — simulates market fills for a day's trade instructions.

Baseline (Sprint 7):
  - Each trade fills at (mid_price + slippage) with a commission
  - If |intended_shares| > max_daily_participation × ADV_20d, spread across
    multiple days (partial_fill=True on all but the last day)
  - Shares are derived from target_notional / mid_price (or from
    delta_weight × AUM / mid_price if notional is 0)

The engine does NOT hold state across days on its own — it emits Fill
records; the equity_curve module aggregates them into daily mark-to-market.
"""
from __future__ import annotations

import hashlib
from datetime import date
from math import floor

from backend.execution.slippage_model import compute_slippage_bps
from backend.execution.commissions    import commission_bps
from backend.execution.types          import Fill


def _txn_id(market: str, ticker: str, fill_date: date, seq: int) -> str:
    """Deterministic transaction id."""
    payload = f"{market}|{ticker}|{fill_date.isoformat()}|{seq}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def simulate_fills(instructions: list[dict],
                     fill_date: date,
                     starting_aum: float,
                     get_mid_price: callable,
                     get_adv_20d_shares: callable,
                     get_vol_20d: callable,
                     get_prior_weight: callable,
                     min_slippage_bps: float,
                     liquidity_impact_bps: float,
                     vol_impact_bps: float,
                     commission_bps_config: float,
                     max_daily_participation: float,
                     market: str,
                     model_stamp: dict | None = None) -> list[Fill]:
    """Simulate fills for a list of TradeInstruction dicts.

    instructions: [{ticker, action, prior_weight, new_weight, delta_weight, reason}, ...]
                    Only OPEN / CLOSE / INCREASE / DECREASE get filled. HOLD skipped.
    fill_date:     the day these fills happen on
    starting_aum:  starting portfolio value in market currency
    get_mid_price: callable(ticker) → mid_price or None
    get_adv_20d_shares / get_vol_20d / get_prior_weight: callables per ticker

    Returns Fill list. Empty when no executable instructions or missing prices.
    """
    if starting_aum <= 0 or not instructions:
        return []
    stamp = dict(model_stamp) if model_stamp else {}

    fills: list[Fill] = []
    seq = 0
    for ins in instructions:
        action = str(ins.get("action") or "HOLD")
        if action == "HOLD": continue

        ticker = str(ins.get("ticker") or "")
        if not ticker: continue

        delta_w = float(ins.get("delta_weight") or 0.0)
        if abs(delta_w) < 1e-9: continue

        mid = get_mid_price(ticker)
        if mid is None or mid <= 0: continue

        adv = get_adv_20d_shares(ticker) or 0.0
        vol = get_vol_20d(ticker) or 0.0
        prior_w = float(ins.get("prior_weight") or get_prior_weight(ticker) or 0.0)
        new_w   = float(ins.get("new_weight")   or (prior_w + delta_w))

        intended_notional = abs(delta_w) * starting_aum
        intended_shares = intended_notional / mid
        direction = +1 if delta_w > 0 else -1
        side = "LONG" if new_w >= 0 else "SHORT"

        # Partial-fill logic
        if adv > 0 and intended_shares > max_daily_participation * adv:
            fillable_today = max_daily_participation * adv
            fill_ratio = float(fillable_today / intended_shares)
            shares_today = float(fillable_today)
            partial = True
        else:
            shares_today = float(intended_shares)
            fill_ratio = 1.0
            partial = False

        # Slippage + commission
        slip_bps = compute_slippage_bps(
            order_size_shares=shares_today, adv_20d_shares=adv,
            vol_20d_annualised=vol,
            min_slippage_bps=min_slippage_bps,
            liquidity_impact_bps=liquidity_impact_bps,
            vol_impact_bps=vol_impact_bps,
            direction=direction,
        )
        fill_price = float(mid * (1.0 + slip_bps / 10_000.0))
        filled_notional = shares_today * fill_price
        comm_bps, comm_amt = commission_bps(commission_bps_config, filled_notional)

        seq += 1
        fills.append(Fill(
            market=market, ticker=ticker, fill_date=fill_date,
            txn_id=_txn_id(market, ticker, fill_date, seq),
            action=action, side=side,
            shares=round(shares_today, 6),
            fill_price=round(fill_price, 4),
            slippage_bps=round(slip_bps, 3),
            commission_bps=round(comm_bps, 3),
            commission_amount=round(comm_amt, 4),
            partial_fill=partial, fill_ratio=round(fill_ratio, 4),
            intended_notional=round(intended_notional, 2),
            filled_notional=round(filled_notional, 2),
            prior_weight=round(prior_w, 6),
            new_weight=round(new_w, 6),
            model_stamp=stamp,
        ))
    return fills
