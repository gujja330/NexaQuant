"""R006 · Phase 2 · Position Lifecycle State Machine.

Addresses Issue #4 (silent vanishing) and #5 (Runner 2 = Top-N screener).

State transitions (each transition writes to portfolio_ledger):

    (none)
       ↓ OPEN or ROTATE_IN
    ACTIVE
       │
       ├── HOLD (still valid · not actionable · stays ACTIVE via HOLD event)
       │
       ├── REBALANCE (allocation adjust · stays ACTIVE)
       │
       ├── ROTATE_OUT → (rotation to another ticker)
       │
       ├── EXIT_STOP → (stop-loss triggered)
       │
       ├── EXIT_TARGET → (T1 or T2 hit)
       │
       ├── EXIT_HORIZON → (holding period expired)
       │
       └── EXIT_MANUAL → (operator override)
                  ↓
             EXITED (terminal · position closed)

Guarantees:
  · No position transitions from ACTIVE to nothing (silently)
  · Every terminal event has a recorded reason
  · Every transition is a ledger event · never a "just disappeared"

Called by Runner 2's daily cycle · never by Runner 1 (which stays sealed).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from .portfolio_ledger import append as ledger_append, current_portfolio_state


@dataclass
class LifecycleDecision:
    ticker: str
    from_state: str            # NEW · ACTIVE · EXITED
    to_state: str
    event: str                 # LedgerEvent value
    reason: str
    price: float | None = None
    linked_to: str | None = None
    linked_from: str | None = None
    edge_pp: float | None = None
    horizon_days: int | None = None
    allocated_pct: float | None = None


def evaluate_position(root: Path, market: str, runner: str, ticker: str,
                          asof: str,
                          current_price: float,
                          stop_price: float | None,
                          t1_price: float | None,
                          t2_price: float | None,
                          horizon_days: int) -> LifecycleDecision | None:
    """Evaluate an existing ACTIVE position · returns a lifecycle decision.

    Returns None if position is still ACTIVE with no state change (i.e.
    still HOLD · no exit trigger). Caller then explicitly logs HOLD event.
    """
    state = current_portfolio_state(root, market, runner)
    pos = state.get(ticker)
    if pos is None or not pos.get("is_active"):
        return None       # not active · no decision to make

    entry_price = pos.get("entry_price") or 0
    opened_on = pos.get("opened_on") or ""

    # ── EXIT_STOP · stop-loss triggered ──
    if stop_price is not None and current_price <= stop_price:
        return LifecycleDecision(
            ticker=ticker, from_state="ACTIVE", to_state="EXITED",
            event="EXIT_STOP",
            reason=f"stop-loss triggered at {current_price:.2f} "
                     f"(stop={stop_price:.2f})",
            price=current_price,
        )

    # ── EXIT_TARGET · T2 (stretch) hit first · else T1 ──
    if t2_price is not None and current_price >= t2_price:
        return LifecycleDecision(
            ticker=ticker, from_state="ACTIVE", to_state="EXITED",
            event="EXIT_TARGET",
            reason=f"T2 (stretch) hit at {current_price:.2f} "
                     f"(T2={t2_price:.2f})",
            price=current_price,
        )
    if t1_price is not None and current_price >= t1_price:
        return LifecycleDecision(
            ticker=ticker, from_state="ACTIVE", to_state="EXITED",
            event="EXIT_TARGET",
            reason=f"T1 hit at {current_price:.2f} (T1={t1_price:.2f})",
            price=current_price,
        )

    # ── EXIT_HORIZON · holding period expired ──
    try:
        opened_dt = date.fromisoformat(opened_on)
        asof_dt = date.fromisoformat(asof)
        days_held = (asof_dt - opened_dt).days
        if horizon_days > 0 and days_held >= horizon_days:
            return LifecycleDecision(
                ticker=ticker, from_state="ACTIVE", to_state="EXITED",
                event="EXIT_HORIZON",
                reason=f"held {days_held}d ≥ horizon {horizon_days}d",
                price=current_price,
            )
    except (ValueError, TypeError):
        pass

    # ── Still ACTIVE · no state change · caller should log HOLD ──
    return None


def log_hold(root: Path, market: str, runner: str, ticker: str, asof: str,
                current_price: float, horizon_days: int) -> None:
    """Explicit HOLD event · addresses Issue #4 (never silent removal).
    Called for every ACTIVE position that didn't transition out."""
    ledger_append(root, market=market, runner=runner, ticker=ticker,
                     event="HOLD", asof=asof, price=current_price,
                     reason="within horizon · no exit trigger · continuing",
                     horizon_days=horizon_days)


def log_open(root: Path, market: str, runner: str, ticker: str, asof: str,
                entry_price: float, horizon_days: int,
                allocated_pct: float | None = None,
                reason: str = "new position") -> None:
    """Log a new position entering the portfolio (Issue #3 · lifecycle)."""
    ledger_append(root, market=market, runner=runner, ticker=ticker,
                     event="OPEN", asof=asof, price=entry_price,
                     reason=reason, horizon_days=horizon_days,
                     allocated_pct=allocated_pct)


def log_rotation(root: Path, market: str, runner: str,
                    out_ticker: str, in_ticker: str, asof: str,
                    out_price: float, in_price: float,
                    edge_pp: float, horizon_days: int,
                    reason: str = "") -> None:
    """Log a matched rotation pair (Issue #6 · audit trail)."""
    r = reason or f"rotate {out_ticker} → {in_ticker} · edge {edge_pp:+.2f}pp"
    ledger_append(root, market=market, runner=runner, ticker=out_ticker,
                     event="ROTATE_OUT", asof=asof, price=out_price,
                     reason=r, linked_to=in_ticker, edge_pp=edge_pp,
                     horizon_days=horizon_days)
    ledger_append(root, market=market, runner=runner, ticker=in_ticker,
                     event="ROTATE_IN", asof=asof, price=in_price,
                     reason=r, linked_from=out_ticker, edge_pp=edge_pp,
                     horizon_days=horizon_days)


def apply_decision(root: Path, market: str, runner: str,
                      decision: LifecycleDecision, asof: str,
                      horizon_days: int) -> None:
    """Persist a lifecycle decision to the ledger."""
    ledger_append(root, market=market, runner=runner, ticker=decision.ticker,
                     event=decision.event, asof=asof, price=decision.price,
                     reason=decision.reason, linked_to=decision.linked_to,
                     linked_from=decision.linked_from, edge_pp=decision.edge_pp,
                     horizon_days=horizon_days,
                     allocated_pct=decision.allocated_pct)
