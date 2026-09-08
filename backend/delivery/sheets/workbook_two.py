"""AEGIS · TWO-SHEET INVESTOR WORKBOOK · CEO 2026-09-08.

    CURRENT        everything AEGIS currently considers INVESTABLE
    EXIT HISTORY   the permanent record of everything that has exited

THIS MODULE RENDERS. IT DOES NOT COMPUTE.
-----------------------------------------
Per the CEO directive:

> "The pipeline must generate the canonical lifecycle dataset first and
>  the XLSX must render only that dataset."

Every value shown here comes from
`reports/context/canonical_lifecycle_{market}.json`, produced upstream by
`backend.delivery.lifecycle.canonical_daily_lifecycle`. This module owns
NO business logic: no stop is derived, no P&L computed, no action
classified, no row filtered.

That is the whole point. Every delivery defect this month came from a
renderer independently reconstructing state - two sheets each computing an
R2 stop and disagreeing about whether a position had hit it. A renderer
that cannot compute cannot disagree with the engine.

If a number looks wrong it is wrong in the lifecycle dataset, and that is
the only place to fix it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# Vocabulary is DEFINED in the lifecycle layer and re-exported here so
# callers and tests have exactly one source for it.
from backend.delivery.lifecycle.canonical_daily_lifecycle import (  # noqa: E402
    ALLOWED_ENGINES, CURRENT_ACTIONS, ENGINE_MOM, ENGINE_R1, ENGINE_R2,
    NON_INVESTABLE_STATES, classify_action, is_investable,
)

TWO_SHEETS = ["CURRENT", "EXIT HISTORY"]

CURRENT_COLUMNS = [
    "Market", "Ticker", "Engine", "Action", "Entry Date", "Entry Price",
    "Current Price", "P&L %", "Confidence %", "Stop", "Stop State",
    "Dist to Stop %", "Max Loss if Stop %", "Target", "Position ID", "Reason",
]

EXIT_COLUMNS = [
    "Exit Date", "Ticker", "Market", "Engine", "Entry Date", "Entry Price",
    "Exit Price", "Realized P&L %", "Holding Days", "Exit Reason",
    "Entry Confidence %", "Exit Trigger", "Position ID", "Source",
]


def _fmt(x, dash="—"):
    return dash if x is None else x


def load_lifecycle(root: Path, market: str, asof: str) -> Optional[dict]:
    """The ONLY input. None when the upstream stage has not run.

    A missing dataset is reported, never silently replaced by recomputing -
    that would recreate the divergence this design exists to remove.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(root, market)
    if d is None:
        return None
    if str(d.get("asof")) != str(asof):
        d = dict(d)
        d["_stale"] = True          # render, but say so
    return d


def emit_current(wb, d: dict):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    rows = d.get("current") or []
    c = d.get("counts") or {}
    ws = wb.create_sheet("CURRENT")
    n = len(CURRENT_COLUMNS)
    _banner(ws, "AEGIS %s · CURRENT · what is investable now · %s"
            % (str(d.get("market", "")).upper(), d.get("asof")), n)
    _sub(ws, ("%d investable · NEW %d · ACTIVE+ %d · ACTIVE %d   ·   "
              "R2 %d · MOMENTUM %d · R1 %d (advisory)"
              % (c.get("current_total", 0), c.get("new", 0),
                 c.get("active_plus", 0), c.get("active", 0),
                 c.get("r2_investable", 0), c.get("momentum_investable", 0),
                 c.get("r1_investable", 0))), n, 2)
    worsts = [r["max_loss_if_stop_pct"] for r in rows
              if isinstance(r.get("max_loss_if_stop_pct"), (int, float))]
    n_breach = c.get("stop_breached", 0)
    if worsts:
        _sub(ws, ("🛡 DOWNSIDE · %d position(s) with an INTACT stop · if all of "
                  "them fired today the average outcome is %.2f%% from entry, "
                  "worst single %.2f%%"
                  % (len(worsts), sum(worsts) / len(worsts), min(worsts))),
             n, 3)
    else:
        _sub(ws, "🛡 DOWNSIDE · no intact stop on any row", n, 3)
    # CEO 2026-09-08 · "Breached means EXIT transition, not CURRENT."
    # A breached position is no longer investable, so it is no longer on
    # this sheet. Say where it went - a row that just vanishes is exactly
    # the silent restatement this design exists to prevent.
    n_bx = c.get("breach_exits", 0)
    if n_bx:
        _sub(ws, ("🔴 %d position(s) left CURRENT on a STOP BREACH (R1 %d · "
                  "R2 %d) and are recorded in EXIT HISTORY with their loss "
                  "intact · %d newly breached today"
                  % (n_bx, c.get("breach_exits_r1", 0),
                     c.get("breach_exits_r2", 0),
                     c.get("breach_exits_new_today", 0))), n, 4)
    # Invariant guard · CURRENT is breach-free by construction upstream.
    # If this ever fires the routing broke and the sheet is wrong.
    if n_breach:
        _sub(ws, ("⛔ CONTRACT VIOLATION · %d BREACHED row(s) reached CURRENT "
                  "· the lifecycle routing failed · do not trade this sheet"
                  % n_breach), n, 4)
    if d.get("_stale"):
        _sub(ws, ("⚠ lifecycle dataset is dated %s, not this report's as-of "
                  "· rerun the pipeline" % d.get("asof")), n, 4)
    _header(ws, CURRENT_COLUMNS, 5)
    for i, w in enumerate([9, 12, 10, 10, 12, 12, 13, 10, 12, 12, 13, 14,
                           17, 12, 30, 50], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    for row in rows:
        _write_row(ws, [
            row.get("market"), row.get("ticker"), row.get("engine"),
            row.get("action"), row.get("entry_date"),
            _fmt(row.get("entry_price")), _fmt(row.get("current_price")),
            _fmt(row.get("pnl_pct")), _fmt(row.get("confidence_pct")),
            _fmt(row.get("stop"), "UNAVAILABLE"),
            row.get("stop_state") or "—",
            _fmt(row.get("dist_to_stop_pct")),
            _fmt(row.get("max_loss_if_stop_pct")), _fmt(row.get("target")),
            row.get("position_id"), row.get("reason"),
        ], r, pnl_col_idx=8)
        r += 1
    if not rows:
        ws.cell(r, 1, "Nothing investable today.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "CURRENT is the daily recommendation · everything AEGIS considers "
        "investable right now. Non-investable states (WATCH, REVIEW, AVOID, "
        "research-only) are filtered from this VIEW · they remain in the "
        "backend research artifacts.",
        "Every value here is rendered from the canonical lifecycle dataset "
        "produced upstream in the same pipeline run. This sheet computes "
        "nothing, so it cannot disagree with the engines.",
        "Engine · R2 production · MOMENTUM upstream (never bypasses R2 "
        "governance) · R1 ADVISORY, which carries no dynamic-exit "
        "protection and is never auto-exited.",
        "Action · NEW (became investable today) · ACTIVE+ (already active, "
        "on a BUY-family signal) · ACTIVE. EXIT never appears here · an "
        "exit moves the row to EXIT HISTORY.",
        "Stop · R2 uses the canonical dynamic_risk_v2 value, ENFORCED. R1 "
        "shows an ATR-14 SUGGESTED level that is advisory and NOT enforced.",
        "Stop State · INTACT (price above the stop) · NO STOP (no stop "
        "could be derived). BREACHED never appears here: a position trading "
        "below its stop is not investable, so it transitions to EXIT "
        "HISTORY the day the breach is first observed.",
        "Dist to Stop % · how far price must fall before the stop fires. "
        "Max Loss if Stop % · worst case FROM ENTRY if the stop fires today.",
        "The breach transition is a DELIVERY rule, not a trading rule. No "
        "engine changed: R1 remains advisory and is still never "
        "auto-exited, R2 keeps its enforced dynamic_risk_v2 stop, and no "
        "position was closed in the registry. Only the investor view moved.",
        "A losing position that is still active stays visible with its "
        "negative P&L. Losses are never hidden or restated.",
    ], r, n)
    return len(rows)


def emit_exit_history(wb, d: dict):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    rows = d.get("exits") or []
    ws = wb.create_sheet("EXIT HISTORY")
    n = len(EXIT_COLUMNS)
    _banner(ws, "AEGIS %s · EXIT HISTORY · every closed position · %s"
            % (str(d.get("market", "")).upper(), d.get("asof")), n)
    by = {}
    for e in rows:
        by[e.get("engine")] = by.get(e.get("engine"), 0) + 1
    _sub(ws, ("%d exits · %s   ·   R1 rows are ADVISORY and are excluded "
              "from production P&L"
              % (len(rows),
                 " · ".join(f"{k} {v}" for k, v in sorted(by.items())))),
         n, 2)
    # A breach mark is not a fill. Saying so on the sheet is the only
    # thing that stops an unrealized loss being read as a closed trade.
    _bx = [e for e in rows if e.get("source") == "lifecycle:stop-breach"]
    if _bx:
        _p = [e["realized_pnl_pct"] for e in _bx
              if isinstance(e.get("realized_pnl_pct"), (int, float))]
        _sub(ws, ("🔴 %d of these are STOP-BREACH exits · the stop was passed "
                  "and the position left CURRENT, but it is NOT sold · price "
                  "and P&L are today's MARK%s"
                  % (len(_bx),
                     (" · avg %+.2f%% · worst %+.2f%%"
                      % (sum(_p) / len(_p), min(_p))) if _p else "")), n, 3)
    _header(ws, EXIT_COLUMNS, 4)
    for i, w in enumerate([12, 12, 9, 10, 12, 12, 12, 15, 13, 26, 15, 30,
                           30, 24], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 5
    for e in rows:
        _write_row(ws, [
            e.get("exit_date"), e.get("ticker"), e.get("market"),
            e.get("engine"), e.get("entry_date"),
            _fmt(e.get("entry_price"), "UNAVAILABLE"),
            _fmt(e.get("exit_price"), "UNAVAILABLE"),
            _fmt(e.get("realized_pnl_pct")), _fmt(e.get("holding_days")),
            e.get("exit_reason"), _fmt(e.get("entry_confidence_pct")),
            e.get("exit_trigger"), e.get("position_id"), e.get("source"),
        ], r, pnl_col_idx=8)
        r += 1
    if not rows:
        ws.cell(r, 1, "No exits recorded.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "Permanent record of every closed R1 / R2 / Momentum position, "
        "rendered from the canonical lifecycle dataset.",
        "Realized P&L % · (Exit − Entry) / Entry · the trade's own result.",
        "Source · registry:production (a real R2 trade) · registry:advisory "
        "(R1 · never counted in production P&L) · registry:administrative "
        "(same-day or zero-delta bookkeeping · not a real trade) · "
        "lifecycle:stop-breach (price passed the stop · the row left "
        "CURRENT and is recorded here).",
        "lifecycle:stop-breach rows are MARKS, not fills. The position is "
        "still open in its engine, Exit Price is the latest close, and "
        "Realized P&L % is the live unrealized figure. They carry their own "
        "source precisely so they are never counted in the realized "
        "win-rate or average return alongside trades that actually closed.",
        "Exit Date on a breach row is the day the breach was FIRST "
        "observed, not today, and it never moves. A position that later "
        "recovers above its stop stays here · recovering does not undo "
        "having passed the stop.",
        "UNAVAILABLE means the canonical price source had no value · never "
        "fabricated and never backfilled from today's state.",
    ], r, n)
    return len(rows)


def build_two_sheet_workbook(root: Path, market: str, asof: str) -> dict:
    """Render the two sheets from the canonical lifecycle dataset."""
    from openpyxl import Workbook

    d = load_lifecycle(root, market, asof)
    if d is None:
        raise RuntimeError(
            "canonical lifecycle dataset missing for %s · run "
            "`python -m backend.delivery.lifecycle.canonical_daily_lifecycle "
            "--market %s --asof %s` first. This renderer consumes that "
            "dataset and deliberately cannot rebuild it." % (market, market, asof))
    wb = Workbook()
    wb.remove(wb.active)
    n_cur = emit_current(wb, d)
    n_exit = emit_exit_history(wb, d)
    assert wb.sheetnames == TWO_SHEETS, (
        "two-sheet contract violated: %s" % wb.sheetnames)
    return {"workbook": wb, "market": market.lower(), "asof": asof,
            "sheets": list(wb.sheetnames), "current_rows": n_cur,
            "exit_rows": n_exit, "lifecycle_stale": bool(d.get("_stale")),
            **(d.get("counts") or {})}
