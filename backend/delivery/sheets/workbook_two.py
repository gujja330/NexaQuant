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
    "Current Price", "P&L %", "Confidence %", "Stop", "Dist to Stop %",
    "Max Loss if Stop %", "Target", "Position ID", "Reason",
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
    n_nostop = sum(1 for r in rows if r.get("stop") is None)
    if worsts:
        _sub(ws, ("🛡 DOWNSIDE · every position carries a stop · if ALL stops "
                  "fired today the average outcome is %.2f%% from entry, "
                  "worst single %.2f%% · %d row(s) without a stop"
                  % (sum(worsts) / len(worsts), min(worsts), n_nostop)), n, 3)
    else:
        _sub(ws, "🛡 DOWNSIDE · no stop available for any row", n, 3)
    if d.get("_stale"):
        _sub(ws, ("⚠ lifecycle dataset is dated %s, not this report's as-of "
                  "· rerun the pipeline" % d.get("asof")), n, 4)
    _header(ws, CURRENT_COLUMNS, 5)
    for i, w in enumerate([9, 12, 10, 10, 12, 12, 13, 10, 12, 12, 14, 17,
                           12, 30, 46], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    for row in rows:
        _write_row(ws, [
            row.get("market"), row.get("ticker"), row.get("engine"),
            row.get("action"), row.get("entry_date"),
            _fmt(row.get("entry_price")), _fmt(row.get("current_price")),
            _fmt(row.get("pnl_pct")), _fmt(row.get("confidence_pct")),
            _fmt(row.get("stop"), "UNAVAILABLE"),
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
        "Dist to Stop % · how far price must fall before the stop fires. "
        "Max Loss if Stop % · worst case FROM ENTRY if it fires today · the "
        "capital genuinely at risk on that position.",
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
        "(same-day or zero-delta bookkeeping · not a real trade).",
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
