"""R006 · Phases 5+6+7 · Portfolio Manager (integrated).

The stateful orchestrator that converts Runner 2's Top-N screener output
into a portfolio-aware decision stream.

Pipeline:

    1. LOAD (Phase 5 · Portfolio Memory)
       · Load current portfolio state from portfolio_ledger.jsonl
       · Know what's already held before making any recommendation

    2. EVALUATE EXISTING (Phase 2 · Lifecycle State Machine)
       · For each currently-held position:
         · check stop/T1/T2/horizon triggers
         · if triggered → log EXIT_* event
         · else → log explicit HOLD event

    3. GENERATE PROPOSALS (Phase 3 · Rotation Hysteresis)
       · For each new candidate:
         · If new capital available (portfolio not full) → propose OPEN
         · If replacing existing lower-scoring position → propose ROTATE
         · Apply hysteresis: min edge · min persistent days · daily cap

    4. OPTIMIZE (Phase 6)
       · Sector caps (max N% per sector)
       · Correlation filter (skip highly-correlated additions)
       · Max-N-rotations per day
       · Priority: highest edge first

    5. EMIT (Phase 7 · Full State on Telegram)
       · Portfolio composition: OPENs + HOLDs + EXITs + ROTATEs
       · Every position has explicit lifecycle event today
       · Nothing silently vanishes

Zero coupling to Runner 1. Zero coupling to delivery engine. Additive only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .portfolio_ledger import current_portfolio_state, load_all_events
from .lifecycle_state_machine import (
    evaluate_position, apply_decision, log_hold, log_open, log_rotation,
    LifecycleDecision,
)
from .rotation_hysteresis import (
    evaluate_proposals, RotationProposal, RotationVerdict,
    MIN_EDGE_PP, MAX_ROTATIONS_PER_DAY,
)
from .horizon_lock import (
    horizon_for_rec, is_dynamic_runner,
    validate_no_position_horizon_mutation,
)


DEFAULT_SECTOR_CAP_PCT = 30.0     # max % of portfolio in one sector
DEFAULT_PORTFOLIO_SIZE = 10        # target number of active positions


@dataclass
class PortfolioSnapshot:
    market: str
    runner: str
    asof: str
    horizon_days: int
    active_positions: dict           # {ticker: {...state...}}
    exits_today: list[dict] = field(default_factory=list)
    holds_today: list[dict] = field(default_factory=list)
    opens_today: list[dict] = field(default_factory=list)
    rotations_today: list[dict] = field(default_factory=list)
    rejected_proposals: list[dict] = field(default_factory=list)
    horizon_check: dict = field(default_factory=dict)


def run_daily_cycle(root: Path, market: str, runner: str, asof: str,
                       recs: Sequence[Mapping],
                       sector_cap_pct: float = DEFAULT_SECTOR_CAP_PCT,
                       portfolio_size: int = DEFAULT_PORTFOLIO_SIZE,
                       ) -> PortfolioSnapshot:
    """R006's stateful cycle · call once per daily pipeline run.

    recs: today's investor_actionable-enriched recommendations · same
    shape as reports/recommendations.json entries
    """
    # ── Phase 4 · dynamic-per-rec horizon (R2) or static (R1) ──
    # Each position takes its OWN horizon at OPEN (per operator directive
    # 2026-08-01 · R2 is fully dynamic · not runner-wide locked)
    dynamic = is_dynamic_runner(root, runner)

    # ── Phase 5 · load current portfolio state ──
    state_before = current_portfolio_state(root, market, runner)
    active = {t: p for t, p in state_before.items() if p.get("is_active")}

    snap = PortfolioSnapshot(
        market=market, runner=runner, asof=asof,
        horizon_days=0,        # 0 for dynamic runner · per-position horizons apply
        active_positions={},
    )

    # ── Phase 2 · evaluate existing positions ──
    # Build lookup of current prices from recs
    px_lookup = {}
    for r in recs:
        t = r.get("ticker") or ""
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        cp = ez.get("current_price")
        if t and cp:
            px_lookup[t] = float(cp)

    for ticker, pos in active.items():
        current_price = px_lookup.get(ticker, pos.get("entry_price") or 0)
        # Find this rec (may not be in today's top-N)
        rec = next((r for r in recs if (r.get("ticker") or "") == ticker), None)
        if rec:
            ez = ((rec.get("position_plan") or {}).get("entry_zone") or {})
            stop_price = ez.get("stop_loss")
            t1_price = ez.get("target_1")
            t2_price = ez.get("target_2")
        else:
            stop_price = t1_price = t2_price = None

        # Use the LOCKED horizon this position was opened with · never mutate
        pos_horizon = pos.get("horizon_days") or (
            horizon_for_rec(root, runner, rec or {}) if dynamic else 60
        )

        decision = evaluate_position(root, market, runner, ticker, asof,
                                          current_price, stop_price, t1_price,
                                          t2_price, pos_horizon)
        if decision is not None:
            apply_decision(root, market, runner, decision, asof, pos_horizon)
            snap.exits_today.append({
                "ticker":       ticker,
                "event":        decision.event,
                "reason":       decision.reason,
                "price":        current_price,
                "horizon_days": pos_horizon,
            })
        else:
            # Explicit HOLD event · addresses Issue #4 · never silent
            log_hold(root, market, runner, ticker, asof, current_price, pos_horizon)
            snap.holds_today.append({
                "ticker":       ticker,
                "price":        current_price,
                "opened_on":    pos.get("opened_on"),
                "days_held":    _days_between(pos.get("opened_on"), asof),
                "horizon_days": pos_horizon,
            })

    # ── Phase 3+6 · generate + hysteresis-filter rotation proposals ──
    still_active = {t for t in active
                        if t not in {e["ticker"] for e in snap.exits_today}}
    proposals = []
    for r in recs:
        ia = r.get("investor_action") or {}
        ri = r.get("rotation_intelligence") or {}
        t = r.get("ticker") or ""
        if not t or t in still_active:
            continue
        if ri.get("should_rotate") and ri.get("replacement_ticker"):
            from_t = t
            to_t = ri.get("replacement_ticker") or ""
            edge = float(ri.get("expected_alpha_delta_pct") or 0)
            proposals.append(RotationProposal(
                from_ticker=from_t, to_ticker=to_t, edge_pp=edge,
                from_price=px_lookup.get(from_t, 0),
                to_price=px_lookup.get(to_t, 0),
            ))

    if proposals:
        verdicts = evaluate_proposals(root, market, runner, asof, proposals)
        approved = [v for v in verdicts if v.approved]
        # Sector cap check on approved
        approved = _apply_sector_cap(root, approved, recs, sector_cap_pct)
        for v in approved:
            # Horizon for the INCOMING position (dynamic-per-rec for R2)
            to_rec = next((r for r in recs
                                if (r.get("ticker") or "") == v.proposal.to_ticker), None)
            in_horizon = horizon_for_rec(root, runner, to_rec or {}) if dynamic else 60
            log_rotation(root, market, runner,
                            out_ticker=v.proposal.from_ticker,
                            in_ticker=v.proposal.to_ticker,
                            asof=asof,
                            out_price=v.proposal.from_price,
                            in_price=v.proposal.to_price,
                            edge_pp=v.proposal.edge_pp,
                            horizon_days=in_horizon)
            snap.rotations_today.append({
                "from":          v.proposal.from_ticker,
                "to":            v.proposal.to_ticker,
                "edge_pp":       v.proposal.edge_pp,
                "in_horizon_days": in_horizon,
            })
        for v in verdicts:
            if not v.approved:
                snap.rejected_proposals.append({
                    "from":    v.proposal.from_ticker,
                    "to":      v.proposal.to_ticker,
                    "edge_pp": v.proposal.edge_pp,
                    "reason":  v.rejected_reason,
                })

    # ── Phase 5 (open new positions when portfolio isn't full) ──
    active_count = len(active) - len(snap.exits_today) + len(snap.rotations_today)
    slots_open = max(0, portfolio_size - active_count)
    if slots_open > 0:
        buy_recs = [r for r in recs
                        if (r.get("investor_action") or {}).get("is_actionable_entry")
                        and (r.get("ticker") or "") not in still_active]
        buy_recs.sort(key=lambda r: -(r.get("ensemble_score") or 0))
        for r in buy_recs[:slots_open]:
            t = r.get("ticker") or ""
            price = px_lookup.get(t, 0)
            alloc = float(((r.get("position_plan") or {}).get("suggested_allocation_pct") or 0))
            # Dynamic horizon · locked at this OPEN · never mutated after
            open_horizon = horizon_for_rec(root, runner, r) if dynamic else 60
            log_open(root, market, runner, t, asof, price, open_horizon,
                        allocated_pct=alloc, reason="new position · slot available")
            snap.opens_today.append({
                "ticker": t, "price": price, "alloc": alloc,
                "horizon_days": open_horizon,
            })

    # ── Phase 4 · horizon-mutation invariant check (per-position lock) ──
    snap.active_positions = current_portfolio_state(root, market, runner)
    snap.horizon_check = validate_no_position_horizon_mutation(root, runner)

    return snap


def _apply_sector_cap(root: Path, verdicts: list[RotationVerdict],
                          recs: Sequence[Mapping],
                          cap_pct: float) -> list[RotationVerdict]:
    """Reject rotations that would push a sector over cap_pct.
    Simplistic first pass · picks by highest edge · rejects duplicates."""
    seen_sectors: dict[str, int] = {}
    kept = []
    sector_lookup = {r.get("ticker"): r.get("sector") for r in recs}
    for v in verdicts:
        sector = sector_lookup.get(v.proposal.to_ticker) or ""
        pct_here = seen_sectors.get(sector, 0) + 10   # rough per-position weight
        if pct_here > cap_pct:
            v.approved = False
            v.rejected_reason = (v.rejected_reason or "") + \
                                     f" · sector cap {cap_pct}% would be exceeded"
            continue
        seen_sectors[sector] = pct_here
        kept.append(v)
    return kept


def _days_between(from_iso: str | None, to_iso: str) -> int:
    if not from_iso:
        return 0
    try:
        return (date.fromisoformat(to_iso) - date.fromisoformat(from_iso)).days
    except (ValueError, TypeError):
        return 0


def snapshot_to_dict(snap: PortfolioSnapshot) -> dict:
    """Serialize snapshot for reports/research/portfolio_snapshot_{market}.json."""
    return {
        "market":              snap.market,
        "runner":              snap.runner,
        "asof":                snap.asof,
        "horizon_days":        snap.horizon_days,
        "n_active_before":     sum(1 for p in snap.active_positions.values()
                                        if p.get("is_active")),
        "n_opens":             len(snap.opens_today),
        "n_holds":             len(snap.holds_today),
        "n_exits":             len(snap.exits_today),
        "n_rotations":         len(snap.rotations_today),
        "n_rejected":          len(snap.rejected_proposals),
        "opens_today":         snap.opens_today,
        "holds_today":         snap.holds_today,
        "exits_today":         snap.exits_today,
        "rotations_today":     snap.rotations_today,
        "rejected_proposals":  snap.rejected_proposals,
        "horizon_check":       snap.horizon_check,
    }


def emit_snapshot(root: Path, snap: PortfolioSnapshot) -> Path:
    """Persist snapshot to reports for Telegram + audit consumers."""
    p = root / "reports" / "research" / f"portfolio_snapshot_{snap.market}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":              "aegis.portfolio.manager.r006.v1",
        "generated_utc":       datetime.now(timezone.utc).isoformat(),
        **snapshot_to_dict(snap),
    }
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
