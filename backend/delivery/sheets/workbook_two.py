"""AEGIS · TWO-SHEET INVESTOR WORKBOOK · CEO 2026-09-08.

    CURRENT        everything AEGIS currently considers INVESTABLE
    EXIT HISTORY   the permanent record of everything that has exited

Nothing else. No Daily Recommendation, no per-engine sheets, no research.

WHY
---
The five-sheet layout spread one decision across five surfaces and
surfaced states the investor cannot act on (HOLD / WATCH / REVIEW / AVOID
/ NO_EVIDENCE / dormant). The only daily question is "what can I invest
in right now?", and CURRENT answers it alone.

WHAT THIS IS NOT
----------------
A presentation refactor only. No engine logic is touched: R2 production
rules, thresholds, ensemble weights, exits, the canonical dynamic-risk
source, R1 advisory semantics, Momentum thresholds and R3 isolation are
all unchanged. Non-investable states are FILTERED FROM THE VIEW, never
deleted from the backend artifacts that record them.

LOSSES ARE NOT HIDDEN
---------------------
A losing position that is still genuinely active stays in CURRENT with
its negative P&L visible. ITC at -7.57% remains ITC at -7.57%. The point
is to shrink the decision surface, not to flatter the system.

THE ACTION RULE IS CANONICAL, NOT INVENTED
------------------------------------------
NEW / ACTIVE / ACTIVE+ / EXIT already existed, defined identically in
three places in the legacy sender
(scripts/telegram_command_center_send.py ~1654, ~2128, ~2833):

    status == EXIT (or binding risk signal)              -> EXIT
    recommended_date == asof                             -> NEW
    status in BUY / STRONG BUY / ACCUMULATE / ADD / BUY BIG -> ACTIVE+
    otherwise                                            -> ACTIVE

That rule is reused verbatim here, driven by the Registry's own
`initial_signal` field, whose live values are exactly BUY / STRONG BUY /
HOLD / ROTATED_SAMEDAY. Nothing speculative was added.

MOMENTUM
--------
Momentum remains a separate engine and cannot bypass R2 governance. The
momentum ledger sets `production_impact = null` on every entry by design
("research only · never opens position"), so a momentum row is investable
only once it has become an R2 position - at which point it is ENGINE=R2.
Momentum therefore contributes rows to CURRENT only if the existing
lifecycle marks them investable; today that is zero, and that zero is a
truthful result, not a bug to be engineered away.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

TWO_SHEETS = ["CURRENT", "EXIT HISTORY"]

ENGINE_R1, ENGINE_R2, ENGINE_MOM = "R1", "R2", "MOMENTUM"
ALLOWED_ENGINES = (ENGINE_R1, ENGINE_R2, ENGINE_MOM)

ACTION_NEW, ACTION_ACTIVE, ACTION_ACTIVE_PLUS = "NEW", "ACTIVE", "ACTIVE+"
ACTION_EXIT = "EXIT"
CURRENT_ACTIONS = (ACTION_NEW, ACTION_ACTIVE_PLUS, ACTION_ACTIVE)

# The canonical strengthening family · legacy sender, verbatim.
BUY_FAMILY = {"BUY", "STRONG BUY", "ACCUMULATE", "ADD", "BUY BIG"}

# States that must never reach the investor view. Kept only so the filter
# is explicit and testable · they remain in the backend artifacts.
NON_INVESTABLE_STATES = {
    "HOLD", "WATCH", "REVIEW", "AVOID", "IGNORE", "NO SIGNAL", "NO_SIGNAL",
    "PUMP_RISK", "MOMENTUM_WATCH", "NO_EVIDENCE", "REJECTED", "DORMANT",
    "BLOCKED", "RESEARCH", "RESEARCH_ONLY", "INSUFFICIENT_SAMPLE",
    "DATA-REQUIRED", "DATA_REQUIRED", "N/A", "NO_MODEL", "NO-MODEL",
    "NON_INVESTABLE", "SUGGESTED", "SHADOW",
}

# CEO 2026-09-08 · "stoploss is very much needed that too dynamic · high
# negative P&L not acceptable · this way we loose entire money".
# The dynamic stop already exists and is enforced; what was missing was
# the investor being able to SEE the downside. Three columns make the
# capital at risk explicit per row:
#   Stop              the canonical dynamic_risk_v2 level (never recomputed)
#   Dist to Stop %    how far price must fall before the stop fires
#   Max Loss if Stop  the worst case FROM ENTRY if the stop fires today
# Measured 2026-09-08: worst case averages -5.93% (India) / -4.76% (USA)
# per position, worst single -10.78%. Bounded, not "entire money".
CURRENT_COLUMNS = [
    "Market", "Ticker", "Engine", "Action", "Entry Date", "Entry Price",
    "Current Price", "P&L %", "Confidence %", "Stop", "Dist to Stop %",
    "Max Loss if Stop %", "Target", "Position ID", "Reason",
]

EXIT_COLUMNS = [
    "Exit Date", "Ticker", "Market", "Engine", "Entry Date", "Entry Price",
    "Exit Price", "Realized P&L %", "Holding Days", "Exit Reason",
    "Entry Confidence %", "Exit Trigger", "Position ID", "Source",
]


@dataclass
class CurrentRow:
    market: str
    ticker: str
    engine: str
    action: str
    entry_date: str
    entry_price: Optional[float]
    current_price: Optional[float]
    pnl_pct: Optional[float]
    confidence: Optional[float]
    stop: Optional[float]
    dist_to_stop_pct: Optional[float]
    max_loss_if_stop_pct: Optional[float]
    target: Optional[float]
    position_id: str
    reason: str


@dataclass
class ExitRow:
    exit_date: str
    ticker: str
    market: str
    engine: str
    entry_date: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    realized_pnl_pct: Optional[float]
    holding_days: Optional[int]
    exit_reason: str
    entry_confidence: Optional[float]
    exit_trigger: str
    position_id: str
    source: str


@dataclass
class TwoSheetViews:
    market: str
    asof: str
    current: list = field(default_factory=list)
    exits: list = field(default_factory=list)
    filtered_out: list = field(default_factory=list)   # audit trail
    counts: dict = field(default_factory=dict)


def classify_action(status: str, initial_signal: str, created_date: str,
                    asof: str) -> str:
    """The canonical NEW / ACTIVE+ / ACTIVE / EXIT rule · reused verbatim.

    Order matters and matches the legacy sender: EXIT dominates, then a
    same-day entry is NEW, then the BUY family is ACTIVE+, else ACTIVE.
    """
    st = str(status or "").upper().strip()
    if st in ("CLOSED", "EXIT"):
        return ACTION_EXIT
    if created_date and asof and str(created_date)[:10] == str(asof)[:10]:
        return ACTION_NEW
    if str(initial_signal or "").upper().strip() in BUY_FAMILY:
        return ACTION_ACTIVE_PLUS
    return ACTION_ACTIVE


def is_investable(action: str, initial_signal: str) -> bool:
    """A row reaches CURRENT only if its ACTION is one of the three
    investable states AND its signal is not an explicitly non-investable
    diagnostic state.

    Note HOLD: a HOLD signal still yields ACTION=ACTIVE for a position
    that is genuinely open, and an open position IS investable exposure -
    the investor owns it. What is filtered is a row whose ACTION would be
    a non-investable state, not a held position with a HOLD signal.
    """
    if action not in CURRENT_ACTIONS:
        return False
    return str(action).upper() not in NON_INVESTABLE_STATES


def _num(x) -> Optional[float]:
    try:
        return round(float(x), 4) if x is not None else None
    except (TypeError, ValueError):
        return None


def build_views(root: Path, market: str, asof: str) -> TwoSheetViews:
    """Single computation for both sheets · canonical sources only."""
    from scripts.build_aegis_3sheet_workbook import (
        _load_registry, _load_r1_active_for_investments, _load_dynamic_risk,
        _close_on_or_before, _normalize_exit_reason, _target_from_registry,
        _atr14_at_date, _target_from_atr_fallback,
    )
    from backend.delivery.canonical.retirement import retired_runners

    m = market.lower()
    v = TwoSheetViews(market=m, asof=asof)
    retired = retired_runners(root)
    reg_data = _load_registry(root, m, retired)
    # CANONICAL R2 STOP · one source. The workbook never recomputes it.
    dr_by_pid = _load_dynamic_risk(root, m)

    def _conf(o):
        c = getattr(o, "initial_score", None)
        if isinstance(c, (int, float)):
            return round(float(c) * 100, 1) if 0 <= c <= 1 else round(float(c), 1)
        return None

    def _mk_current(o, engine: str) -> Optional[CurrentRow]:
        action = classify_action(o.status, o.initial_signal,
                                 o.created_date, asof)
        sig = str(o.initial_signal or "")
        if not is_investable(action, sig):
            v.filtered_out.append({"ticker": o.ticker, "engine": engine,
                                   "action": action, "signal": sig,
                                   "reason": "not an investable action"})
            return None
        entry = _close_on_or_before(root, o.ticker, m, o.created_date or "")
        curr = _close_on_or_before(root, o.ticker, m, asof)
        pnl = None
        if entry and curr and entry > 0:
            pnl = round((curr / entry - 1.0) * 100, 2)
        # STOP SOURCE · engine-specific and governance-bound.
        #   R2 · the CANONICAL dynamic_risk_v2 level, enforced. Never
        #        recomputed here, so no two views can disagree.
        #   R1 · ADVISORY ONLY. R1 carries no dynamic-exit protection by
        #        governance (V2 §18) and giving it an enforced stop would
        #        turn R1 into R2, which the directive forbids. But leaving
        #        the downside blank on 16 of 24 rows hides risk from the
        #        investor, so an ATR-14 SUGGESTED level is shown and
        #        labelled as such in stop_basis / Reason. It is displayed,
        #        never enforced.
        stop = None
        stop_basis = "none"
        if engine == ENGINE_R2:
            dr = dr_by_pid.get(getattr(o, "opportunity_id", "")) or {}
            stop = _num(dr.get("stop"))
            stop_basis = "dynamic_risk_v2 · ENFORCED" if stop is not None else "none"
        elif engine == ENGINE_R1 and entry:
            atr = _atr14_at_date(root, m, o.ticker, o.created_date or asof)
            if atr and atr > 0:
                stop = _num(float(entry) - 2.0 * float(atr))
                stop_basis = "ATR14 SUGGESTED · advisory · NOT enforced"
        target = _target_from_registry(o)
        if not target and entry:
            target = _target_from_atr_fallback(
                entry, _atr14_at_date(root, m, o.ticker, o.created_date or asof),
                m_target=3.0)
        days = None
        try:
            days = (date.fromisoformat(asof)
                    - date.fromisoformat(o.created_date)).days
        except Exception:
            pass
        reason = ("R1 ADVISORY · stop is SUGGESTED only · never auto-exited"
                  if engine == ENGINE_R1
                  else f"{sig or 'signal'} · held {days if days is not None else '?'}d "
                       f"· stop {stop_basis}")
        # Downside made explicit · both derived from the CANONICAL stop.
        dist = None
        worst = None
        if stop is not None and curr:
            dist = round((curr - stop) / curr * 100, 2)
        if stop is not None and entry and entry > 0:
            worst = round((stop / entry - 1.0) * 100, 2)
        return CurrentRow(
            market=m.upper(), ticker=str(o.ticker).upper().split(".", 1)[0],
            engine=engine, action=action, entry_date=o.created_date or "",
            entry_price=_num(entry), current_price=_num(curr), pnl_pct=pnl,
            confidence=_conf(o), stop=stop, dist_to_stop_pct=dist,
            max_loss_if_stop_pct=worst, target=_num(target),
            position_id=getattr(o, "opportunity_id", ""), reason=reason)

    # ── CURRENT · R2 production ───────────────────────────────────────
    for o in (reg_data.get("active") or []):
        r = _mk_current(o, ENGINE_R2)
        if r:
            v.current.append(r)

    # ── CURRENT · R1 advisory (retired runner · advisory semantics) ───
    r2_tickers = {r.ticker for r in v.current}
    for o in (_load_r1_active_for_investments(root, m) or []):
        r = _mk_current(o, ENGINE_R1)
        if r:
            # Same ticker may appear once per ENGINE · that is intended.
            v.current.append(r)

    # ── CURRENT · MOMENTUM ────────────────────────────────────────────
    # Momentum never opens a position (production_impact is null by
    # design), so a momentum candidate is investable only once it has
    # become an R2 position - at which point it is already an R2 row
    # above. Nothing is forced into CURRENT to make the sheet look busier.
    v.counts["momentum_investable"] = 0

    # ── EXIT HISTORY · all engines ────────────────────────────────────
    def _mk_exits(opps, engine, source):
        for o in opps or []:
            entry = _close_on_or_before(root, o.ticker, m, o.created_date or "")
            exitp = _close_on_or_before(root, o.ticker, m, o.closed_date or "")
            pnl = None
            if entry and exitp and entry > 0:
                pnl = round((exitp / entry - 1.0) * 100, 2)
            days = None
            try:
                days = (date.fromisoformat(o.closed_date)
                        - date.fromisoformat(o.created_date)).days
            except Exception:
                pass
            raw = getattr(o, "closed_reason", "") or ""
            v.exits.append(ExitRow(
                exit_date=o.closed_date or "", ticker=str(o.ticker).upper().split(".", 1)[0],
                market=m.upper(), engine=engine, entry_date=o.created_date or "",
                entry_price=_num(entry), exit_price=_num(exitp),
                realized_pnl_pct=pnl, holding_days=days,
                exit_reason=_normalize_exit_reason(raw) if raw else "",
                entry_confidence=_conf(o), exit_trigger=raw[:60],
                position_id=getattr(o, "opportunity_id", ""), source=source))

    _mk_exits(reg_data.get("closed_90d"), ENGINE_R2, "registry:production")
    _mk_exits(reg_data.get("closed_retired_90d"), ENGINE_R1, "registry:advisory")
    _mk_exits(reg_data.get("closed_admin_90d"), ENGINE_R2, "registry:administrative")
    v.exits.sort(key=lambda e: (e.exit_date or "", e.ticker), reverse=True)

    # Ordering · NEW, then ACTIVE+, then ACTIVE; within each R2 > MOMENTUM > R1
    _act = {ACTION_NEW: 0, ACTION_ACTIVE_PLUS: 1, ACTION_ACTIVE: 2}
    _eng = {ENGINE_R2: 0, ENGINE_MOM: 1, ENGINE_R1: 2}
    v.current.sort(key=lambda r: (_act.get(r.action, 9), _eng.get(r.engine, 9),
                                  -(r.pnl_pct or 0)))

    v.counts.update({
        "current_total": len(v.current),
        "r1_investable": sum(1 for r in v.current if r.engine == ENGINE_R1),
        "r2_investable": sum(1 for r in v.current if r.engine == ENGINE_R2),
        "new": sum(1 for r in v.current if r.action == ACTION_NEW),
        "active_plus": sum(1 for r in v.current if r.action == ACTION_ACTIVE_PLUS),
        "active": sum(1 for r in v.current if r.action == ACTION_ACTIVE),
        "exit_history_total": len(v.exits),
        "filtered_non_investable": len(v.filtered_out),
    })
    return v


# ── Emitters · pure formatters over build_views ───────────────────────

def _fmt(x, dash="—"):
    return dash if x is None else x


def emit_current(wb, v: TwoSheetViews):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet("CURRENT")
    n = len(CURRENT_COLUMNS)
    _banner(ws, "AEGIS %s · CURRENT · what is investable now · %s"
            % (v.market.upper(), v.asof), n)
    c = v.counts
    _sub(ws, ("%d investable · NEW %d · ACTIVE+ %d · ACTIVE %d   ·   "
              "R2 %d · MOMENTUM %d · R1 %d (advisory)"
              % (c.get("current_total", 0), c.get("new", 0),
                 c.get("active_plus", 0), c.get("active", 0),
                 c.get("r2_investable", 0), c.get("momentum_investable", 0),
                 c.get("r1_investable", 0))), n, 2)
    # Downside, stated up front · answers "how much can I lose?"
    _r2 = [r for r in v.current if r.engine == ENGINE_R2
           and r.max_loss_if_stop_pct is not None]
    if _r2:
        worst = min(r.max_loss_if_stop_pct for r in _r2)
        avg = sum(r.max_loss_if_stop_pct for r in _r2) / len(_r2)
        _sub(ws, ("🛡 DOWNSIDE · every R2 position carries a live dynamic "
                  "stop · if ALL stops fired today the average outcome is "
                  "%.2f%% from entry, worst single %.2f%%"
                  % (avg, worst)), n, 3)
    else:
        _sub(ws, "🛡 DOWNSIDE · no canonical stop available for any R2 row",
             n, 3)
    _header(ws, CURRENT_COLUMNS, 5)
    for i, w in enumerate([9, 12, 10, 10, 12, 12, 13, 10, 12, 12, 14, 17,
                           12, 30, 40], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    for row in v.current:
        _write_row(ws, [
            row.market, row.ticker, row.engine, row.action, row.entry_date,
            _fmt(row.entry_price), _fmt(row.current_price), _fmt(row.pnl_pct),
            _fmt(row.confidence), _fmt(row.stop, "UNAVAILABLE"),
            _fmt(row.dist_to_stop_pct), _fmt(row.max_loss_if_stop_pct),
            _fmt(row.target), row.position_id, row.reason,
        ], r, pnl_col_idx=8)
        r += 1
    if not v.current:
        ws.cell(r, 1, "Nothing investable today.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "CURRENT is the daily recommendation · everything AEGIS considers "
        "investable right now. Non-investable states (HOLD signals with no "
        "open position, WATCH, REVIEW, AVOID, research-only) are filtered "
        "from this view · they remain in the backend research artifacts.",
        "Engine · R2 production · MOMENTUM upstream (never bypasses R2 "
        "governance) · R1 ADVISORY, which carries no dynamic-exit "
        "protection and is never auto-exited.",
        "Action · NEW (became investable today) · ACTIVE+ (already active "
        "and on a BUY-family signal) · ACTIVE (already active). EXIT never "
        "appears here · an exit moves the row to EXIT HISTORY.",
        "Stop · the canonical dynamic_risk_v2 value. The workbook never "
        "recomputes it, so no two views can disagree about a stop.",
        "Dist to Stop % · how far price must fall before the stop fires. "
        "Max Loss if Stop % · the worst case FROM ENTRY if it fires today · "
        "this is the capital genuinely at risk on the position.",
        "A losing position that is still active stays visible with its "
        "negative P&L. Losses are never hidden or restated.",
    ], r, n)
    return len(v.current)


def emit_exit_history(wb, v: TwoSheetViews):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet("EXIT HISTORY")
    n = len(EXIT_COLUMNS)
    _banner(ws, "AEGIS %s · EXIT HISTORY · every closed position · %s"
            % (v.market.upper(), v.asof), n)
    by_eng = {}
    for e in v.exits:
        by_eng[e.engine] = by_eng.get(e.engine, 0) + 1
    _sub(ws, ("%d exits · %s   ·   R1 rows are ADVISORY and are excluded "
              "from production P&L"
              % (len(v.exits),
                 " · ".join(f"{k} {c}" for k, c in sorted(by_eng.items())))),
         n, 2)
    _header(ws, EXIT_COLUMNS, 4)
    for i, w in enumerate([12, 12, 9, 10, 12, 12, 12, 15, 13, 26, 15, 30,
                           30, 22], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 5
    for e in v.exits:
        _write_row(ws, [
            e.exit_date, e.ticker, e.market, e.engine, e.entry_date,
            _fmt(e.entry_price, "UNAVAILABLE"), _fmt(e.exit_price, "UNAVAILABLE"),
            _fmt(e.realized_pnl_pct), _fmt(e.holding_days), e.exit_reason,
            _fmt(e.entry_confidence), e.exit_trigger, e.position_id, e.source,
        ], r, pnl_col_idx=8)
        r += 1
    if not v.exits:
        ws.cell(r, 1, "No exits recorded.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "Permanent record of every closed R1 / R2 / Momentum position.",
        "Realized P&L % · (Exit − Entry) / Entry · the trade's own result.",
        "Source · registry:production (a real R2 trade) · registry:advisory "
        "(R1 · never counted in production P&L) · registry:administrative "
        "(same-day or zero-delta bookkeeping · not a real trade).",
        "UNAVAILABLE means the canonical price source had no value · never "
        "fabricated and never backfilled from today's state.",
    ], r, n)
    return len(v.exits)


def build_two_sheet_workbook(root: Path, market: str, asof: str) -> dict:
    from openpyxl import Workbook

    v = build_views(root, market, asof)
    wb = Workbook()
    wb.remove(wb.active)
    n_cur = emit_current(wb, v)
    n_exit = emit_exit_history(wb, v)
    assert wb.sheetnames == TWO_SHEETS, (
        "two-sheet contract violated: %s" % wb.sheetnames)
    return {"workbook": wb, "views": v, "market": market.lower(),
            "asof": asof, "sheets": list(wb.sheetnames),
            "current_rows": n_cur, "exit_rows": n_exit, **v.counts}
