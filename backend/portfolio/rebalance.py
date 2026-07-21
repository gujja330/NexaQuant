"""Rebalance diff — compare yesterday's holdings to today's target."""
from __future__ import annotations

from datetime import date

from backend.portfolio.types import (
    Position, PortfolioSnapshot, PortfolioDiff, TradeInstruction, TradeAction,
)


def diff_portfolios(prior: PortfolioSnapshot | None,
                      current: PortfolioSnapshot,
                      rebalance_threshold_bps: int = 25) -> PortfolioDiff:
    """Return the TradeInstruction list needed to move prior → current.

    Rebalance threshold is expressed in bps of portfolio (25 = 0.25%).
    Positions whose |delta_weight| <= threshold are marked HOLD (no trade needed).
    """
    thresh = rebalance_threshold_bps / 10_000.0

    prior_map = {p.ticker: p.weight for p in (prior.positions if prior else [])}
    curr_map  = {p.ticker: p.weight for p in current.positions}
    all_tickers = sorted(set(prior_map) | set(curr_map))

    instr: list[TradeInstruction] = []
    n_open = n_close = n_inc = n_dec = n_hold = 0
    turnover_sum = 0.0

    for t in all_tickers:
        pw = prior_map.get(t, 0.0)
        nw = curr_map.get(t, 0.0)
        d  = nw - pw
        turnover_sum += abs(d)

        if pw == 0.0 and abs(nw) > 1e-9:
            action = TradeAction.OPEN;  n_open += 1
            reason = f"open new position at weight {nw:+.4f}"
        elif abs(pw) > 1e-9 and nw == 0.0:
            action = TradeAction.CLOSE; n_close += 1
            reason = f"exit prior position (was {pw:+.4f})"
        elif abs(d) <= thresh:
            action = TradeAction.HOLD; n_hold += 1
            reason = f"|Δ|={abs(d):.5f} ≤ threshold ({thresh:.5f})"
        elif d > 0:
            action = TradeAction.INCREASE; n_inc += 1
            reason = f"increase from {pw:+.4f} to {nw:+.4f} (Δ={d:+.4f})"
        else:
            action = TradeAction.DECREASE; n_dec += 1
            reason = f"decrease from {pw:+.4f} to {nw:+.4f} (Δ={d:+.4f})"

        instr.append(TradeInstruction(
            ticker=t, action=action,
            prior_weight=round(pw, 6), new_weight=round(nw, 6),
            delta_weight=round(d, 6),
            reason=reason,
        ))

    return PortfolioDiff(
        market=current.market, asof=current.asof,
        n_open=n_open, n_close=n_close,
        n_increase=n_inc, n_decrease=n_dec, n_hold=n_hold,
        turnover_pct=round(turnover_sum / 2.0, 5),   # sum of |Δ|/2 is convention
        instructions=instr,
        rebalance_threshold_bps=rebalance_threshold_bps,
        prior_asof=(prior.asof if prior else None),
    )
