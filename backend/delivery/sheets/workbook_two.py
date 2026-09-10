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

import json
from pathlib import Path
from typing import Optional

# Vocabulary is DEFINED in the lifecycle layer and re-exported here so
# callers and tests have exactly one source for it.
from backend.delivery.lifecycle.canonical_daily_lifecycle import (  # noqa: E402
    ALLOWED_ENGINES, CURRENT_ACTIONS, ENGINE_MOM, ENGINE_R1, ENGINE_R2,
    NON_INVESTABLE_STATES, classify_action, is_investable,
)

TWO_SHEETS = ["CURRENT", "EXIT HISTORY"]

# R2's own columns. Nothing in the R3 block below may ever be inserted
# among these - the separation is the point.
# CEO 2026-09-10 lock audit. Five columns added and two renamed:
#
#   Admission Status   · 33 India names admitted 09-09 rendered ACTIVE+
#                        with no cohort visible, so yesterday's NEW looked
#                        like it had vanished.
#   Market Data As-of  · the sheet showed 09-09 closes under a 09-10
#                        header and said nothing about the difference.
#   Sector             · carried at 100% in canonical and simply not
#                        rendered.
#   Current Market Cap · labelled CURRENT because no PIT cap history
#                        exists. Never liquidity.
#   Size               · reported beside the cap, never instead of it.
#
#   "Current Price"   -> "Last Price"        (it is the last close, not a live quote)
#   "Dist to Stop %"  -> "Stop Distance %"
CURRENT_COLUMNS_R2 = [
    "Market", "Ticker", "Engine", "Action", "Admission Status",
    "Entry Date", "Entry Price", "Last Price", "Market Data As-of",
    "P&L %", "Confidence %", "Sector", "Current Market Cap",
    "Market Cap As-of", "Size",
    "Stop", "Stop State", "Stop Distance %", "Max Loss if Stop %",
    "Target", "Position ID", "Reason",
]

# R3 SHADOW INTELLIGENCE · research only.
#
# These columns describe an R2 candidate; they never alter one. R2 Action
# is decided before this block is read and is not a function of anything
# in it. Today every value is ABSTAIN / IMMATURE because no specialist has
# validated - and that is the honest reading, not a placeholder.
# CEO 2026-09-08 · ONE column. The first version exposed eleven -
# Decision, Evidence, Risk, Fundamental, Statistical, Temporal, Sector,
# Uncertainty, Reason, As-of, Model - to communicate a single fact: R3 is
# not yet validated. That is research plumbing sitting beside a trader's
# Stop column, and terms like INSUFFICIENT_SUBSTRATE and
# NOT_AVAILABLE_AT_ASOF are audit language, not decision language.
#
# The full specialist decomposition is NOT deleted. It lives in the shadow
# ledger and the research artifacts, where auditability belongs. What
# reaches the operational sheet is the governed disposition and a short
# human-readable reason.
CURRENT_COLUMNS_R3 = ["R3 SHADOW"]

CURRENT_COLUMNS = CURRENT_COLUMNS_R2 + CURRENT_COLUMNS_R3

# R3 comments on R2 candidates only · it has nothing to say about an R1
# advisory row and must not pretend otherwise.
R3_ENGINES = ("R2", "MOMENTUM", "MOM")
R3_NOT_APPLICABLE = "NOT_APPLICABLE"

# `Record Type` is the population; `Source` is the provenance. They are
# different questions and the audit proved they disagree: 463 USA rows
# came from `registry:production` but were orphan auto-closes.
#
# `Realized P&L %` was renamed to `P&L %` because 529 of USA's 547 rows
# are NOT realized - 490 orphan reconstructions and 5 open breach marks.
# A column header is a claim, and that one was false for 97% of the sheet.
EXIT_COLUMNS = [
    "Exit Date", "Ticker", "Sector", "Market", "Engine", "Record Type",
    "Entry Date", "Entry Price", "Exit Price", "P&L %", "Holding Days",
    "Exit Reason", "Entry Confidence %", "Exit Trigger", "Position ID",
    "Source",
]


def _fmt(x, dash="—"):
    return dash if x is None else x


def load_funnel(root: Path, market: str) -> Optional[dict]:
    """The reconciler's one-line verdict · rendered verbatim, never derived.

    CEO 2026-09-08 · "Every NEW = 0 must show the exact bottleneck /
    rejection reason." CURRENT stated a bare "NEW 0" for six days while
    the explanation sat in artifacts nothing ran. The renderer still
    computes nothing - it renders a second dataset alongside the first.
    """
    from backend.delivery.lifecycle import why_not_current as wnc
    return wnc.load(root, market)


def load_r3_shadow(root: Path, market: str, asof: str) -> dict:
    """R3 decisions for this as-of, keyed by ticker · {} when absent.

    Read as a FILE, exactly like `load_funnel` reads the reconciler's
    verdict. The renderer still computes nothing; it renders a second
    dataset alongside the first. Reading the ledger rather than importing
    backend.research keeps the dependency one-way and file-based, so the
    R3 isolation audit stays true in both directions.
    """
    p = (root / "reports" / "research" / "r3" / "shadow"
         / f"ledger_{market.lower()}.jsonl")
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if str(r.get("as_of"))[:10] != str(asof)[:10]:
            continue
        out[str(r.get("ticker") or "").upper()] = r
    return out


def r3_cells(rec: Optional[dict], engine: str) -> list:
    """The single R3 cell for one row · never invents a value.

    ABSTAIN means INSUFFICIENT VALIDATED EVIDENCE. It is not HOLD, not
    BUY, not AVOID, and not a 50/50 probability. No probability is
    rendered at all: producing "52%" from an uncalibrated model would be
    false precision, and months later nobody could tell it apart from a
    number that meant something.
    """
    if str(engine or "").upper() not in R3_ENGINES:
        return ["N/A · R3 evaluates R2 candidates only"]
    if not rec:
        return ["NOT_EVALUATED · no R3 snapshot for this date"]
    action = str(rec.get("r3_action") or "ABSTAIN").upper()
    if action == "ABSTAIN":
        return ["ABSTAIN · R3 not yet validated"]
    # Once a specialist earns evidence the cell names it. AVOID is a
    # research annotation and never implies an R2 EXIT.
    who = ", ".join(rec.get("contributing_specialists") or []) or "R3"
    return ["%s · %s" % (action, who)]


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
    _r3 = d.get("_r3") or {}
    ws = wb.create_sheet("CURRENT")
    n = len(CURRENT_COLUMNS)
    # The header date is the WORKBOOK date. The prices are the last
    # completed close, which on a pre-close run is the previous session.
    # Both are stated, because showing only the first invites the reader
    # to assume the prices are today's.
    _mda = d.get("market_data_asof")
    _banner(ws, ("AEGIS %s · CURRENT · what is investable now · "
                 "workbook %s · prices = %s close"
                 % (str(d.get("market", "")).upper(), d.get("asof"),
                    _mda or "UNKNOWN")), n)
    # SAME-CLOSE ADMISSION · why a row can read exactly 0.00%.
    #
    # 33 India rows showed 0.00% on 2026-09-10. They were admitted at the
    # 2026-09-09 close and are still marked at that same close, so entry
    # and last price are the same number. Verified against the bars
    # (ABBOTINDIA entry 25455.0 = 09-09 close 25455.0). That is correct,
    # but a screen full of zeros looks like a broken price feed, so it is
    # named rather than left for the reader to work out.
    _same = [r for r in rows
             if r.get("pnl_pct") == 0
             and str(r.get("entry_date") or "")[:10] == str(_mda or "")[:10]]
    _same_note = ("   ·   %d row(s) read 0.00%%: admitted at the %s close "
                  "and still marked at it (same-close admission, not a "
                  "stale price)" % (len(_same), _mda)) if _same else ""
    _sub(ws, ("%d investable · NEW %d · ACTIVE+ %d · ACTIVE %d   ·   "
              "R2 %d · MOMENTUM %d · R1 %d (advisory)%s"
              % (c.get("current_total", 0), c.get("new", 0),
                 c.get("active_plus", 0), c.get("active", 0),
                 c.get("r2_investable", 0), c.get("momentum_investable", 0),
                 c.get("r1_investable", 0), _same_note)), n, 2)
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

    # WHY IS NEW ZERO? · rendered from the lifecycle reconciler.
    fn = d.get("_funnel") or {}
    if fn.get("headline"):
        _sub(ws, "🔎 " + str(fn["headline"]), n, 5)

    # STALE INPUTS · "Reject stale inputs from becoming CURRENT."
    # India's recommendation artifact sat five days old while CURRENT was
    # rebuilt every cycle and looked entirely normal. Staleness that is not
    # displayed is indistinguishable from freshness.
    # Row 6 carries BOTH the stale-input warning and the R3 notice. They
    # are joined rather than written twice: a second _sub on the same row
    # overwrites the first, and a stale-data warning silently replaced by
    # an R3 banner is exactly the kind of quiet loss this sheet exists to
    # prevent. If a third message ever needs row 6, add it to this list.
    _row6 = []
    _st = d.get("stale_inputs") or []
    if _st:
        _row6.append("⛔ STALE INPUT · %s · CURRENT is built on decisions "
                     "older than this report's as-of · treat NEW/ACTIVE with "
                     "caution"
                     % " · ".join("%s %s (%s day(s) old)"
                                  % (x["input"], x["verdict"], x["age_days"])
                                  for x in _st))
    _n_r3 = sum(1 for k in _r3)
    _row6.append(
        "🤖 R3 SHADOW INTELLIGENCE — RESEARCH ONLY. R3 reviews R2 "
        "candidates but does NOT change R2 Action, Confidence, Stop or "
        "Position. ABSTAIN means R3 has no validated opinion yet — it is "
        "NOT Hold, Buy, Avoid, or a 50/50 probability. A future AVOID is a "
        "research annotation and never implies an R2 EXIT. R3 can become "
        "actionable only after out-of-sample validation, calibration, "
        "incremental-value evidence and explicit authorisation. "
        "%d candidate(s) evaluated today." % _n_r3)
    _sub(ws, "   ||   ".join(_row6), n, 6)
    _header(ws, CURRENT_COLUMNS, 7)
    # A capitalisation is a 12-digit number. Left raw it reads as noise
    # (213353612143.8); grouped it reads as a size. The stored value is
    # unchanged - this is display only, so a reader can still compute on
    # the cell.
    _cap_col = CURRENT_COLUMNS.index("Current Market Cap") + 1
    for i, w in enumerate([9, 12, 10, 10, 20, 12, 12, 13, 17, 10, 22,
                           20, 18, 16, 8, 12, 13, 15, 17, 12, 30, 50,
                           # R3 shadow · one column
                           40], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 8
    for row in rows:
        _write_row(ws, [
            row.get("market"), row.get("ticker"), row.get("engine"),
            row.get("action"),
            row.get("admission_status") or "—",
            row.get("entry_date"),
            _fmt(row.get("entry_price")), _fmt(row.get("current_price")),
            _fmt(row.get("market_data_asof"), "UNAVAILABLE"),
            _fmt(row.get("pnl_pct")),
            # A bare em-dash on a confidence cell reads as a rendering
            # gap. Where the registry genuinely holds no entry score the
            # cell says so instead of leaving the reader to guess.
            _fmt(row.get("confidence_pct"), "Historical score unavailable"),
            _fmt(row.get("sector"), "NOT_AVAILABLE"),
            # Never a liquidity bucket wearing a cap label. India's
            # fundamentals feed carries no capitalisation at all (0/228),
            # so India says so rather than borrowing avg_dv_60d.
            _fmt(row.get("market_cap"), "MARKET_CAP_UNAVAILABLE"),
            _fmt(row.get("market_cap_asof"), "—"),
            _fmt(row.get("size"), "—"),
            _fmt(row.get("stop"), "UNAVAILABLE"),
            row.get("stop_state") or "—",
            _fmt(row.get("dist_to_stop_pct")),
            _fmt(row.get("max_loss_if_stop_pct")),
            # A target at or below the current price is a target already
            # passed · it is not a target and is withheld rather than
            # shown. Four R1 advisory rows carried one on 2026-09-09
            # (CRM: 221.57 against a current 249.12).
            _fmt(None if (isinstance(row.get("target"), (int, float))
                          and isinstance(row.get("current_price"), (int, float))
                          and row["target"] <= row["current_price"])
                 else row.get("target")),
            row.get("position_id"), row.get("reason"),
            # ── R3 SHADOW · appended AFTER every R2 column, never among
            #    them. R2 Action above was decided without reading any of
            #    this and does not change because of it.
            *r3_cells(_r3.get(str(row.get("ticker") or "").upper()),
                      row.get("engine")),
        ], r, pnl_col_idx=10)
        _c = ws.cell(r, _cap_col)
        if isinstance(_c.value, (int, float)):
            _c.number_format = "#,##0"
        r += 1
    if not rows:
        ws.cell(r, 1, "Nothing investable today.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "Stop distance % · the DOWNSIDE from the current price to the "
        "stop. It is not a profit target and no target is implied by it.",
        "Target · withheld (—) when the stored target sits at or below the "
        "current price · a target already passed is not a target.",
        "R3 SHADOW is RESEARCH ONLY. It describes an R2 candidate and never "
        "changes one · R2 Action, Confidence and Stop in this row were "
        "decided without reading any R3 value.",
        "ABSTAIN = insufficient validated evidence. It is NOT Hold, Buy, "
        "Avoid, or a 50/50 probability. Every row reads ABSTAIN today "
        "because no R3 specialist has passed its evidence gate.",
        "A future AVOID is a research annotation · it never implies an R2 "
        "EXIT. Only explicit authorisation can make R3 actionable.",
        "No probability is shown. An uncalibrated model can always produce "
        "a number; months later nobody could tell it apart from one that "
        "meant something.",
        "The full specialist decomposition (fundamental · statistical · "
        "temporal · sector · risk · uncertainty · model version · evidence "
        "tier · OOS · calibration · provenance) is kept in the R3 shadow "
        "ledger and research artifacts · it belongs in the audit trail, not "
        "beside a Stop price.",

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
        "The 🔎 line answers \"why is NEW zero today?\" from the lifecycle "
        "reconciler · every scored name gets exactly one verdict "
        "(reports/context/why_not_current_{market}.json). A zero here is "
        "never presented without its reason.",
    ], r, n)
    return len(rows)


def emit_exit_history(wb, d: dict):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    rows = d.get("exits") or []
    ws = wb.create_sheet("EXIT HISTORY")
    n = len(EXIT_COLUMNS)
    # "every closed position" was an overclaim: canonical coverage starts
    # 2026-08-04 (India) / 2026-08-10 (USA). Nothing before that exists in
    # a provable source, so the claim is narrowed rather than the history
    # invented.
    _banner(ws, "AEGIS %s · EXIT HISTORY · %s"
            % (str(d.get("market", "")).upper(), d.get("asof")), n)
    _dates = sorted(str(e.get("exit_date"))[:10] for e in rows
                    if e.get("exit_date"))
    _cov = ("Canonical lifecycle historical coverage begins %s · earlier "
            "closures are not held in any provable AEGIS source"
            % _dates[0]) if _dates else "No closure history recorded."

    # The four populations, never summed. Realized production performance
    # is reported on its own line and on its own denominator.
    _by_rt = {}
    for e in rows:
        k = e.get("record_type") or "UNCLASSIFIED"
        _by_rt[k] = _by_rt.get(k, 0) + 1
    _real = [e for e in rows if e.get("record_type") == "REALIZED EXIT"]
    _rp = [e["realized_pnl_pct"] for e in _real
           if isinstance(e.get("realized_pnl_pct"), (int, float))]
    _sub(ws, ("%d records · %s   ·   %s"
              % (len(rows),
                 " · ".join("%s %d" % (k, v)
                            for k, v in sorted(_by_rt.items())),
                 _cov)), n, 2)
    # A breach mark is not a fill, and an orphan auto-close is not a
    # trade. Both are named here rather than on their own banner row,
    # because the header must stay on row 4 - three consumers still hold
    # a private copy of that offset, which is the A19/A23 bug class.
    _bx = [e for e in rows if e.get("record_type") == "STOP-BREACH MARK"]
    _sub(ws, ("📊 REALIZED PRODUCTION PERFORMANCE · %d closed trade(s)%s   "
              "·   EXCLUDED from this line: orphan auto-closes, "
              "administrative records, advisory rows, and %d STOP-BREACH "
              "MARK(s) whose stop was passed but which are NOT sold - "
              "their price and P&L are today's mark, not a realized result"
              % (len(_real),
                 (" · win %d/%d · avg %+.2f%%"
                  % (sum(1 for x in _rp if x > 0), len(_rp),
                     sum(_rp) / len(_rp))) if _rp else "",
                 len(_bx))), n, 3)
    _header(ws, EXIT_COLUMNS, 4)
    for i, w in enumerate([12, 12, 20, 9, 10, 20, 12, 12, 12, 15, 13, 26,
                           15, 30, 30, 24], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 5
    for e in rows:
        _write_row(ws, [
            e.get("exit_date"), e.get("ticker"),
            # Rendered, not resolved · the lifecycle layer attached this
            # from the canonical sector cache. Deriving it here would
            # create a second sector source, which is what the renderer
            # exists to avoid.
            _fmt(e.get("sector"), "NOT_AVAILABLE"),
            e.get("market"),
            e.get("engine"),
            e.get("record_type") or "UNCLASSIFIED",
            e.get("entry_date"),
            _fmt(e.get("entry_price"), "UNAVAILABLE"),
            _fmt(e.get("exit_price"), "UNAVAILABLE"),
            _fmt(e.get("realized_pnl_pct")), _fmt(e.get("holding_days")),
            e.get("exit_reason"),
            # A bare em-dash reads as "nothing here". The registry holds
            # NO entry score for any closed position (0/57 India, 0/562
            # USA), so the honest cell says why it is empty.
            _fmt(e.get("entry_confidence_pct"), "Historical score unavailable"),
            e.get("exit_trigger"), e.get("position_id"), e.get("source"),
        ], r, pnl_col_idx=10)
        r += 1
    if not rows:
        ws.cell(r, 1, "No exits recorded.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        # The banner's overclaim was removed and this line still carried
        # it. A legend is read as authoritative and must not restate a
        # coverage claim the data cannot support.
        "Closed positions held by the canonical lifecycle dataset. Coverage "
        "begins on the date named in the banner · AEGIS had no position "
        "registry before then, only a recommendation list with expiry "
        "semantics, so earlier closures cannot be proven and are not "
        "invented.",
        "P&L % · (Exit − Entry) / Entry. It is a REALIZED result only on a "
        "REALIZED EXIT row · on every other Record Type it is a mark.",
        "Record Type is the population; Source is the provenance. They are "
        "different questions and they disagree: 463 USA rows arrived from "
        "registry:production yet are ORPHAN AUTO-CLOSE. Build performance "
        "statistics on Record Type, never on Source.",
        "REALIZED EXIT · a trade that actually closed · the only population "
        "in the realized performance line. ORPHAN AUTO-CLOSE · a "
        "reconstructed record for a position that was never properly "
        "tracked · not a trade. ADMINISTRATIVE · same-day or zero-delta "
        "bookkeeping · not a trade. ADVISORY/HISTORICAL · retired R1 · "
        "never counted in production P&L. STOP-BREACH MARK · the price "
        "passed the stop and the row left CURRENT.",
        "STOP-BREACH MARK rows are MARKS, not fills. The position is still "
        "open in its engine, Exit Price is the latest close, and P&L % is "
        "the live unrealized figure. They carry their own Record Type "
        "precisely so they are never counted in the realized win-rate or "
        "average return alongside trades that actually closed.",
        "Exit Date on a breach row is the day the breach was FIRST "
        "observed, not today, and it never moves. A position that later "
        "recovers above its stop stays here · recovering does not undo "
        "having passed the stop.",
        "UNAVAILABLE means the canonical price source had no value · never "
        "fabricated and never backfilled from today's state.",
        "Sector · the company's CURRENT classification from the canonical "
        "sector cache, not its sector as of the exit date. No "
        "point-in-time sector history exists, so this column describes the "
        "company today and must not be read as evidence about what the "
        "sector was when the trade was live. NOT_AVAILABLE means the "
        "canonical source has no entry · it is never guessed.",
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
    f = load_funnel(root, market)
    if f is not None:
        d = dict(d)
        d["_funnel"] = f
    # R3 shadow intelligence · a THIRD dataset rendered alongside, never
    # merged into, the lifecycle. Absent shadow ledger renders as
    # NOT_EVALUATED rather than blanks.
    d = dict(d)
    d["_r3"] = load_r3_shadow(root, market, asof)
    wb = Workbook()
    wb.remove(wb.active)
    n_cur = emit_current(wb, d)
    n_exit = emit_exit_history(wb, d)
    assert wb.sheetnames == TWO_SHEETS, (
        "two-sheet contract violated: %s" % wb.sheetnames)
    return {"workbook": wb, "market": market.lower(), "asof": asof,
            "sheets": list(wb.sheetnames), "current_rows": n_cur,
            "exit_rows": n_exit, "lifecycle_stale": bool(d.get("_stale")),
            "stale_inputs": len(d.get("stale_inputs") or []),
            "funnel_headline": (d.get("_funnel") or {}).get("headline"),
            **(d.get("counts") or {})}
