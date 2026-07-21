"""Equity curve — daily mark-to-market of the simulated book.

Sprint 7 baseline: uses Fill records + the closing prices per day to produce
an EquityPoint per (market, date). Because Sprint 7 only has TODAY's data in
production (no historical fills yet), the equity curve on live runs is a
single-point series. The synthetic-input tests exercise the full multi-day path.
"""
from __future__ import annotations

from datetime import date

from backend.execution.types import Fill, EquityPoint


def compute_equity_curve(fills: list[Fill], starting_aum: float,
                            close_price_lookup: callable,
                            trade_dates: list[date],
                            market: str) -> list[EquityPoint]:
    """Build a per-day equity curve from a list of fills.

    Args:
      fills:              deterministic list of Fill records
      starting_aum:       market-currency starting portfolio value
      close_price_lookup: callable(date, ticker) → close price
      trade_dates:        sorted list of dates to mark
      market:             "india" | "usa"

    Returns:
      List[EquityPoint] in chronological order.
    """
    if not trade_dates or starting_aum <= 0:
        return []

    # Running positions: ticker → {shares, entry_price, side}
    positions: dict[str, dict] = {}
    cash = float(starting_aum)
    curve: list[EquityPoint] = []
    prev_equity = starting_aum

    fills_by_date: dict[date, list[Fill]] = {}
    for f in fills:
        fills_by_date.setdefault(f.fill_date, []).append(f)

    for d in sorted(trade_dates):
        # Apply today's fills to running state
        for f in fills_by_date.get(d, []):
            sign = +1 if f.side == "LONG" else -1
            if f.action == "OPEN" or f.action == "INCREASE":
                cash -= sign * f.filled_notional         # long: cash out; short: cash in
                cash -= f.commission_amount              # commission always debits
                pos = positions.setdefault(f.ticker, {"shares": 0.0, "cost_basis": 0.0, "side": f.side})
                pos["shares"] += sign * f.shares
                pos["cost_basis"] += sign * f.filled_notional
                pos["side"] = f.side
            elif f.action == "CLOSE" or f.action == "DECREASE":
                cash += sign * f.filled_notional
                cash -= f.commission_amount
                pos = positions.get(f.ticker)
                if pos:
                    pos["shares"] -= sign * f.shares
                    pos["cost_basis"] -= sign * f.filled_notional
                    if abs(pos["shares"]) < 1e-9:
                        positions.pop(f.ticker, None)

        # Mark to market at day's close
        long_notional = 0.0; short_notional = 0.0
        for ticker, pos in positions.items():
            px = close_price_lookup(d, ticker)
            if px is None: continue
            val = pos["shares"] * float(px)
            if val > 0: long_notional += val
            else:       short_notional += val    # negative
        equity = cash + long_notional + short_notional

        daily_ret = (equity / prev_equity - 1.0) if prev_equity > 0 else 0.0
        cum_ret   = (equity / starting_aum - 1.0) if starting_aum > 0 else 0.0

        curve.append(EquityPoint(
            date=d,
            equity_value=round(equity, 4),
            cash=round(cash, 4),
            long_notional=round(long_notional, 4),
            short_notional=round(short_notional, 4),
            n_positions=len(positions),
            daily_return_pct=round(daily_ret, 6),
            cumulative_return_pct=round(cum_ret, 6),
        ))
        prev_equity = equity

    return curve
