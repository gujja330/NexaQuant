"""R006 · Phase 1 · Portfolio Ledger · append-only event log.

Post-mortem 2026-07-31 addresses Issue #6 (rotation source inconsistent · no
audit trail) and #4 (positions vanish silently · no exit event).

Every meaningful portfolio event MUST be appended to
`reports/research/portfolio_ledger.jsonl` with:

    ts_utc         · when the event was recorded
    asof           · trading date the event belongs to
    market         · india · usa
    runner         · runner1 · runner2 (which engine caused this event)
    ticker         · symbol affected
    event          · OPEN · HOLD · ROTATE_OUT · ROTATE_IN · EXIT_STOP
                     · EXIT_TARGET · EXIT_HORIZON · EXIT_MANUAL · REBALANCE
    price          · fill price for the event
    reason         · short human string · why this event happened
    linked_from    · ticker the position rotated FROM (only on ROTATE_IN)
    linked_to      · ticker the position rotated TO (only on ROTATE_OUT)
    edge_pp        · alpha edge in pp (only on ROTATE_*)
    horizon_days   · locked horizon of this runner's position

Append-only. Never overwrite. Never delete. The ledger is the audit trail
for every single portfolio decision · so no future incident like the
2026-07-31 disappearance ("yesterday LUPIN · today TCS · where did the
rotation go?") can ever be untraceable again.

Loaded by every daily pipeline run at the top of Runner 2's cycle so
the engine has PORTFOLIO MEMORY (Issue #10).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

LedgerEvent = Literal[
    "OPEN",           # first entry into portfolio
    "HOLD",           # explicit hold decision (never silent)
    "ROTATE_OUT",     # closing this position to fund a rotation
    "ROTATE_IN",      # entering this position via rotation
    "EXIT_STOP",      # stop-loss triggered
    "EXIT_TARGET",    # T1 or T2 hit
    "EXIT_HORIZON",   # holding period expired
    "EXIT_MANUAL",    # operator/CEO override
    "REBALANCE",      # allocation adjustment without full close
]


@dataclass
class PortfolioEvent:
    ts_utc: str
    asof: str
    market: str
    runner: str
    ticker: str
    event: str                # one of LedgerEvent values
    price: float | None = None
    reason: str = ""
    linked_from: str | None = None
    linked_to: str | None = None
    edge_pp: float | None = None
    horizon_days: int | None = None
    allocated_pct: float | None = None


def _ledger_path(root: Path) -> Path:
    p = root / "reports" / "research" / "portfolio_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_event(root: Path, event: PortfolioEvent) -> None:
    """Append a single event · atomic per line · never overwrites."""
    p = _ledger_path(root)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(event), default=str, ensure_ascii=False) + "\n")


def append(root: Path, market: str, runner: str, ticker: str,
              event: str, asof: str | None = None,
              price: float | None = None,
              reason: str = "",
              linked_from: str | None = None,
              linked_to: str | None = None,
              edge_pp: float | None = None,
              horizon_days: int | None = None,
              allocated_pct: float | None = None) -> PortfolioEvent:
    """Convenience helper · builds + appends a PortfolioEvent."""
    e = PortfolioEvent(
        ts_utc=datetime.now(timezone.utc).isoformat(),
        asof=asof or date.today().isoformat(),
        market=market,
        runner=runner,
        ticker=ticker,
        event=event,
        price=price,
        reason=reason,
        linked_from=linked_from,
        linked_to=linked_to,
        edge_pp=edge_pp,
        horizon_days=horizon_days,
        allocated_pct=allocated_pct,
    )
    append_event(root, e)
    return e


def load_all_events(root: Path,
                       market: str | None = None,
                       runner: str | None = None,
                       ticker: str | None = None,
                       since_asof: str | None = None) -> list[PortfolioEvent]:
    """Load events matching filters · in chronological order."""
    p = _ledger_path(root)
    if not p.exists():
        return []
    events: list[PortfolioEvent] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if market and d.get("market") != market:
                continue
            if runner and d.get("runner") != runner:
                continue
            if ticker and d.get("ticker") != ticker:
                continue
            if since_asof and (d.get("asof") or "") < since_asof:
                continue
            events.append(PortfolioEvent(**{k: d.get(k) for k
                                                 in PortfolioEvent.__dataclass_fields__}))
    except Exception:
        return events
    return events


def current_portfolio_state(root: Path, market: str, runner: str,
                              asof: str | None = None) -> dict:
    """Reconstruct current portfolio state from ledger events.

    Returns: {ticker: {opened_on, entry_price, horizon_days, allocated_pct,
                        last_event, is_active}}

    A position is `is_active=True` if its last event was OPEN, ROTATE_IN,
    HOLD, or REBALANCE · and False if its last event was any EXIT_* or
    ROTATE_OUT.
    """
    events = load_all_events(root, market=market, runner=runner)
    state: dict[str, dict] = {}
    for e in events:
        t = e.ticker
        exit_events = {"EXIT_STOP", "EXIT_TARGET", "EXIT_HORIZON",
                          "EXIT_MANUAL", "ROTATE_OUT"}
        if e.event == "OPEN" or e.event == "ROTATE_IN":
            state[t] = {
                "opened_on":     e.asof,
                "entry_price":   e.price,
                "horizon_days":  e.horizon_days,
                "allocated_pct": e.allocated_pct,
                "last_event":    e.event,
                "last_event_ts": e.ts_utc,
                "is_active":     True,
            }
        elif e.event in ("HOLD", "REBALANCE"):
            if t in state:
                state[t]["last_event"] = e.event
                state[t]["last_event_ts"] = e.ts_utc
                if e.allocated_pct is not None:
                    state[t]["allocated_pct"] = e.allocated_pct
                state[t]["is_active"] = True
        elif e.event in exit_events:
            if t in state:
                state[t]["last_event"] = e.event
                state[t]["last_event_ts"] = e.ts_utc
                state[t]["exit_reason"] = e.reason
                state[t]["is_active"] = False

    if asof:
        # Filter to positions still active as-of that date · could refine later
        pass
    return state


def rotation_history(root: Path, market: str, runner: str,
                        since_asof: str | None = None) -> list[dict]:
    """Extract rotation pairs (ROTATE_OUT → ROTATE_IN) for audit trail.

    Returns list of {asof, from_ticker, to_ticker, edge_pp, reason}
    · answers 'where did yesterday's rotation go' (Issue #6).
    """
    events = load_all_events(root, market=market, runner=runner,
                                 since_asof=since_asof)
    out_events = [e for e in events if e.event == "ROTATE_OUT"]
    in_events = [e for e in events if e.event == "ROTATE_IN"]
    pairs = []
    for out in out_events:
        matched = next((i for i in in_events
                            if i.asof == out.asof and i.linked_from == out.ticker), None)
        pairs.append({
            "asof":        out.asof,
            "from_ticker": out.ticker,
            "to_ticker":   out.linked_to or (matched.ticker if matched else None),
            "edge_pp":     out.edge_pp,
            "reason":      out.reason,
            "matched_in":  bool(matched),
        })
    return pairs
