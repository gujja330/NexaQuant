"""AEGIS · Unified daily detail history · XLSX (Excel) + optional Google Sheets.

Per operator directives 2026-08-01:
    "instead cant u send an xlsx to telegram with columns and rows by
     each stock"
    "runner 1, runner 2 u can mix into a column called Run_type"
    "or maintain one sheet add country too?"
    "everyday we can update same sheet"

Design:
  · ONE unified XLSX · one row per (Date, Country, Run_Type, Ticker)
  · 38 columns (Date + Country + Run_Type first · then the full stock card
    fields · sortable + filterable in Excel)
  · Daily runs APPEND to the same file (never overwrite)
  · Dedup key = (Date, Country, Run_Type, Ticker) · re-running same day
    updates the existing row (not duplicate)

Output: reports/telegram/aegis_history.xlsx (one file · grows daily)
        reports/telegram/aegis_daily_{asof}.xlsx (today-only snapshot)

Optional: GSHEETS_CREDS_JSON + GSHEETS_SHEET_ID env vars enable Google
Sheets mirror. Silent no-op if creds absent.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .detail_report import (
    _load_position, _load_ledger_events_for_ticker,
    _lifecycle_state, _exit_triggers_checklist,
    _drivers_from_attribution, _r1_orphan_to_rec_shape,
)
from .command_center import _company_name, _short_ticker


# XLSX schema v2 · 33 columns · every field populated with real data today.
# Operator 2026-08-01: "too much of technicals? ur call to decide else keep it"
# CEO decision: dropped 9 R007-blocked columns that were empty for months
# (Exit Triggers Hit · Risk Flags · Sector Exposure % · Confidence Band Low ·
#  Confidence Band High · Correlation · Hist Win Rate · Hist Median Ret ·
#  Hist Avg Hold). Restore as v3 when Ticket R007 lands with the data.
COLUMNS = [
    ("Date",                12),
    ("Country",             10),
    ("Run_Type",            10),      # "R1" | "R2"
    ("Ticker",              12),
    ("Company",             22),
    ("Status",              12),
    ("Exit Reason",         22),     # NEW · populated only when Status = EXIT
    ("Exit P&L %",          12),     # NEW · realized return on exit · blank otherwise
    ("Rank",                6),
    ("Prior Rank",          10),     # NEW · rank at asof-1 (from rank_history)
    ("Rank Δ",              8),      # NEW · today - prior · positive = worse
    ("Health",              8),      # Sprint A · composite 0-100
    ("Band",                14),     # Sprint A · STRONG_BUY/HOLD/WATCH/REVIEW/EXIT_CANDIDATE
    ("Adj Conf",            10),     # CIL · adjusted confidence after context layer
    ("Ctx Drag",            10),     # CIL · signed drag/boost pts vs base confidence
    ("Ctx Reason",          50),     # CIL · top context drivers
    ("Story",               60),     # Sprint C · compact narrative "Rank ↑ 5→1 · Conf +7% · momentum ↑ · 34d left · HOLD"
    ("Alert",               34),     # NEW · profit-protection signals (severity·trigger·note)
    ("Confidence %",        13),
    ("Conf Type",           11),
    ("Model Score",         12),
    ("Day",                 6),
    ("Horizon (d)",         12),
    ("Days Left",           10),
    ("Recommended",         14),
    ("Current Price",       14),
    ("Entry Price",         12),
    ("Buy Zone Low",        13),
    ("Buy Zone High",       13),
    ("Stop Loss",           11),
    ("Risk %",              9),
    ("Target 1",            11),
    ("T1 %",                8),
    ("Target 2",            11),
    ("T2 %",                8),
    ("Today Move %",        13),     # NEW · today's daily change (yesterday_close → today_close)
    ("Current Perf %",      15),
    ("Max Gain %",          12),
    ("Max DD %",            11),
    ("Lifecycle State",     16),
    ("Top Drivers",         32),
    ("Sector",              20),
    ("Portfolio Weight %",  18),
    ("Expected Alpha %",    17),
    ("Last Updated (UTC)",  20),
]

DEDUP_KEY_COLS = ["Date", "Country", "Run_Type", "Ticker"]

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
STATUS_FILLS = {
    "STRONG BUY":  PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid"),
    "BUY":     PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
    "BUY":         PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
    "HOLD":        PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid"),
    "EXIT":        PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid"),
    "ROTATE OUT":  PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid"),
}
CENTER = Alignment(horizontal="center", vertical="center")
LEFT   = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT  = Alignment(horizontal="right", vertical="center")


def _pct_from_range(base, target):
    if not (base and target and base > 0):
        return None
    return (target - base) / base * 100


def _today_move_pct(root: Path, ticker: str, market: str) -> float | None:
    """Compute today's daily price change from bar cache.
    (today_close - yesterday_close) / yesterday_close × 100.
    Falls back to None if cache missing or fewer than 2 bars."""
    try:
        import pandas as pd
    except ImportError:
        return None
    bare = ticker.strip()
    for suf in (".NS", ".BO", ".NSE", ".BSE"):
        if bare.upper().endswith(suf):
            bare = bare[: -len(suf)]
            break
    if market == "usa":
        p = root / "data" / "raw" / "us" / f"{bare}_D1.parquet"
    else:
        p = root / "data" / "raw" / "india" / f"{bare}_D1.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if len(df) < 2:
            return None
        today = float(df["close"].iloc[-1])
        yest = float(df["close"].iloc[-2])
        if yest <= 0:
            return None
        return round((today / yest - 1) * 100, 2)
    except Exception:
        return None


def _rec_to_row(rec: Mapping, market: str, root: Path,
                    runner: str, asof: str) -> list:
    raw_ticker = rec.get("ticker") or "?"
    ticker = _short_ticker(raw_ticker)
    company = _company_name(raw_ticker, market) or ""

    ia = rec.get("investor_action") or {}
    pp = rec.get("position_plan") or {}
    ez = pp.get("entry_zone") or {}
    ev = rec.get("evolution") or {}
    ri = rec.get("rotation_intelligence") or {}

    entry_action = str(ia.get("entry") or "").upper()
    pct_action = str(rec.get("percentile_action") or "").upper()
    if_holding = ia.get("if_holding")

    # Operator 2026-08-01: "then keep as exit only" · 4-state vocab locked:
    # STRONG BUY · BUY · HOLD · EXIT
    # Rotations collapse into EXIT · from action standpoint both mean "sell".
    # Rotation intent still visible in Expected Alpha % column + Command
    # Center rotation section + R006 rotation ledger audit trail.
    #
    # Operator 2026-08-04: "strong buy to new buy is confusing man" — old
    # label "NEW BUY" wrongly implied "newly added today" but actually meant
    # "actionable BUY that isn't top-percentile STRONG_BUY". Renamed to plain
    # "BUY" so STRONG BUY → BUY reads correctly as conviction downgrade ·
    # not a lifecycle contradiction. HCLTECH was the example (rank 2 STRONG
    # BUY Aug 3 → rank 3 BUY Aug 4 · same actionable position · lower conviction).
    if entry_action == "SELL" or if_holding in ("EXIT", "REDUCE", "SELL") \
            or ri.get("should_rotate"):
        status = "EXIT"
    elif entry_action == "BUY" and pct_action == "STRONG_BUY":
        status = "STRONG BUY"
    elif entry_action == "BUY":
        status = "BUY"
    else:
        status = "HOLD"

    # Exit Reason · populated ONLY when status = EXIT · else blank
    exit_reason = ""
    if status == "EXIT":
        risks = (rec.get("why") or {}).get("top_risks") or []
        risk_first = str(risks[0])[:80] if risks else ""
        if ri.get("should_rotate"):
            to_t = ri.get("replacement_ticker") or ""
            edge = ri.get("expected_alpha_delta_pct")
            edge_str = f" (+{edge:.1f}pp)" if edge else ""
            exit_reason = f"Rotation → {to_t}{edge_str}"
        elif if_holding == "EXIT":
            exit_reason = risk_first or "Exit signal (defensive)"
        elif if_holding == "REDUCE":
            exit_reason = risk_first or "Reduce position (defensive)"
        elif entry_action == "SELL":
            exit_reason = risk_first or "Sell signal"
        else:
            exit_reason = risk_first or "Exit trigger"

    rank = rec.get("rank")
    conf_cal = rec.get("calibrated_confidence")
    conf_raw = rec.get("confidence")
    if isinstance(conf_cal, (int, float)) and conf_cal:
        conf_pct = round(conf_cal * 100, 1)
        conf_type = "Calibrated"
    elif isinstance(conf_raw, (int, float)) and conf_raw:
        conf_pct = round(conf_raw * 100, 1)
        conf_type = "Raw"
    else:
        conf_pct = None
        conf_type = "—"

    ensemble_score = rec.get("ensemble_score")
    if isinstance(ensemble_score, (int, float)):
        model_score = round(ensemble_score if ensemble_score > 5 else ensemble_score * 100, 1)
    else:
        model_score = None

    horizon = pp.get("time_horizon_days") or 0
    days_rec = ev.get("days_recommended") or 0
    days_left = max(0, horizon - days_rec + 1) if horizon else None

    current_price = ez.get("current_price")
    ps = _load_position(root, market, ticker)
    entry_price = first_seen = high_water = low_water = None
    if ps:
        entry_price = ps.get("first_seen_price")
        first_seen = ps.get("first_seen_date")
        high_water = ps.get("high_water_price")
        low_water = ps.get("low_water_price")
        if current_price is None:
            current_price = ps.get("last_seen_price")

    # Fallback: if position store has no entry yet (rec just appeared today),
    # use current_price as entry so downstream columns have a reference · this
    # matches R006 lifecycle intent (position OPENS at today's price when new).
    if entry_price is None and current_price:
        entry_price = current_price
        if not first_seen:
            first_seen = asof

    stop = ez.get("stop_loss")
    t1 = ez.get("target_1")
    t2 = ez.get("target_2")

    # Bug fix 2026-08-01: engine only populates stop/T1/T2 for actionable BUYs.
    # For HOLD picks (and R1 defensives), derive standard defaults so operator
    # gets SAME field coverage per stock (5% stop, 8% T1, 15% T2 · heuristics
    # documented in AEGIS_STOCK_CARD_FORMAT.md). Never fabricates per-stock.
    ref_price = entry_price or current_price
    if ref_price:
        if stop is None:
            stop = round(ref_price * 0.95, 2)         # -5% default stop
        if t1 is None:
            t1 = round(ref_price * 1.08, 2)           # +8% default T1
        if t2 is None:
            t2 = round(ref_price * 1.15, 2)           # +15% default T2
    if t2 is None and t1 is not None and current_price:
        t2 = current_price + (t1 - current_price) * 1.5

    # Buy Zone default (±1% of ref_price) when engine doesn't emit for HOLDs
    buy_low = ez.get("ideal_buy_low")
    buy_high = ez.get("ideal_buy_high")
    if buy_low is None and ref_price:
        buy_low = round(ref_price * 0.99, 2)
    if buy_high is None and ref_price:
        buy_high = round(ref_price * 1.01, 2)

    base_for_pct = entry_price or current_price
    risk_pct = _pct_from_range(base_for_pct, stop)
    t1_pct = _pct_from_range(base_for_pct, t1)
    t2_pct = _pct_from_range(base_for_pct, t2)

    cur_ret = round((current_price / entry_price - 1) * 100, 2) if (entry_price and current_price) else None
    max_gain = round((high_water / entry_price - 1) * 100, 2) if (entry_price and high_water) else None
    max_dd = round((low_water / entry_price - 1) * 100, 2) if (entry_price and low_water) else None
    today_move = _today_move_pct(root, raw_ticker, market)

    events = _load_ledger_events_for_ticker(root, market, ticker)
    state = _lifecycle_state(events)
    triggers = [label for (label, hit) in _exit_triggers_checklist(events) if hit]
    triggers_str = ", ".join(triggers)

    drivers = _drivers_from_attribution(rec)
    drivers_str = " · ".join(drivers)

    sector = rec.get("sector") or ""
    alloc = pp.get("suggested_allocation_pct")
    exp_alpha = ri.get("expected_alpha_delta_pct")
    if exp_alpha is None and t1 and base_for_pct:
        exp_alpha = round(((t1 / base_for_pct) - 1) * 100, 2)

    country = market.upper()

    # XLSX v2 · 33 columns · every value is real or documented default
    # · R007-blocked columns removed (Risk Flags · Sector Exposure ·
    #   Confidence Band · Correlation · Historical Setups) · will
    #   restore as v3 when R007 lands
    # Exit P&L % · realized return · populated ONLY when Status = EXIT
    # Uses (current_price - entry_price) / entry_price · same as cur_ret
    # but explicitly separated so blank rows in this column = "not exited"
    exit_pnl_pct = ""
    if status == "EXIT" and cur_ret is not None:
        exit_pnl_pct = cur_ret

    # ── Prior Rank + Rank Δ (v5 · 2026-08-04) ──
    # Reads yesterday's rank from rank_history.jsonl so operator can judge
    # day-over-day at a glance ("TCS was #1 Aug 3 · now #9 Aug 4 · Δ +8")
    # instead of comparing two XLSX files manually.
    prior_rank = ""
    rank_delta = ""
    if rank:
        try:
            from backend.portfolio.rank_history import get_prior_rank as _gpr
            _pr, _ = _gpr(root, market, "runner2" if runner == "R2" else "runner1",
                              ticker, asof)
            if _pr is not None:
                prior_rank = _pr
                rank_delta = int(rank) - int(_pr)
        except Exception:
            pass

    # Alert · profit-protection signals for this ticker (severity · trigger · note)
    alert = _load_alert(root, market, ticker)

    # Sprint A · Health Score (composite 0-100 + band)
    health_score = ""
    health_band = ""
    prior_band = None
    try:
        hs = _load_health_card(root, market, ticker)
        if hs:
            health_score = hs.get("overall") or ""
            health_band = (hs.get("band") or "").replace("_", " ")
            prior_band = hs.get("prior_band")
    except Exception:
        pass

    # CIL · Adjusted Confidence · Drag · Reason
    adj_conf = ""
    ctx_drag = ""
    ctx_reason = ""
    try:
        cil = _load_cil_adjustment(root, market, ticker)
        if cil:
            adj_conf = cil.get("adjusted")
            ctx_drag = cil.get("drag_pts")
            ctx_reason = cil.get("story") or ""
    except Exception:
        pass

    # Sprint C · Story column · compact narrative
    story = _build_story(rank, prior_rank, rank_delta, conf_pct, ev,
                                health_band, prior_band, days_left, status,
                                if_holding, ri)

    return [
        asof, country, runner, ticker, company, status,
        exit_reason,          # NEW · blank unless status = EXIT
        exit_pnl_pct,         # NEW · realized P&L % · blank unless EXIT
        rank if rank else "",
        prior_rank,           # NEW v5 · rank at asof-1
        rank_delta,           # NEW v5 · today - prior · +ve = worse rank
        health_score,         # Sprint A · composite 0-100
        health_band,          # Sprint A · band
        adj_conf,             # CIL · adjusted confidence
        ctx_drag,             # CIL · signed drag pts
        ctx_reason,           # CIL · top drivers
        story,                # Sprint C · compact narrative
        alert,                # NEW v5 · profit-protection signals
        conf_pct if conf_pct is not None else "",
        conf_type,
        model_score if model_score is not None else "",
        days_rec if days_rec else "",
        horizon if horizon else "",
        days_left if days_left is not None else "",
        first_seen if first_seen else "",
        current_price if current_price else "",
        entry_price if entry_price else "",
        buy_low if buy_low else "",
        buy_high if buy_high else "",
        stop if stop else "",
        round(risk_pct, 2) if risk_pct is not None else "",
        t1 if t1 else "",
        round(t1_pct, 2) if t1_pct is not None else "",
        t2 if t2 else "",
        round(t2_pct, 2) if t2_pct is not None else "",
        today_move if today_move is not None else "",
        cur_ret if cur_ret is not None else "",
        max_gain if max_gain is not None else "",
        max_dd if max_dd is not None else "",
        state,
        drivers_str,
        sector,
        alloc if alloc else "",
        round(exp_alpha, 2) if exp_alpha is not None else "",
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ]


def _collect_rows_for_market(root: Path, market: str, asof: str) -> list[list]:
    """Return all rows (R2 + R1 if India) for one market on this asof."""
    recs_path = (root / "usa" / "reports" / "recommendations.json"
                    if market == "usa" else root / "reports" / "recommendations.json")
    if not recs_path.exists():
        return []
    payload = json.loads(recs_path.read_text(encoding="utf-8"))
    rows = []
    for r in payload.get("recommendations") or []:
        rows.append(_rec_to_row(r, market, root, runner="R2", asof=asof))
    if market == "india":
        rv = payload.get("runner1_validation") or {}
        for i, o in enumerate(rv.get("runner1_orphans") or [], start=1):
            r1_rec = _r1_orphan_to_rec_shape(o, market)
            # R1 orphans have no explicit rank in payload · derive from list
            # order (already sorted by strength/score in ranking-CSV upstream)
            r1_rec.setdefault("rank", i)
            rows.append(_rec_to_row(r1_rec, market, root, runner="R1", asof=asof))
    return rows


def _load_cil_adjustment(root: Path, market: str, ticker: str) -> dict | None:
    """CIL · load per-ticker adjustment from most-recent CIL run."""
    p = root / "reports" / "context" / f"cil_run_{market}.json"
    if not p.exists(): return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        short = ticker.replace(".NS", "").replace(".BO", "")
        for a in d.get("adjustments") or []:
            t = a.get("ticker") or ""
            if t == ticker or t == short \
                or t.replace(".NS", "").replace(".BO", "") == short:
                return a
    except Exception:
        return None
    return None


def _build_story(rank, prior_rank, rank_delta, conf_pct, ev: dict,
                     health_band: str, prior_band: str | None,
                     days_left, status: str, if_holding, ri: dict) -> str:
    """Sprint C · compose one-line narrative like:
       'Rank ↑ 5→1 · Conf 42% · momentum ↑ · sector leader · 34d left · HOLD'
    Skips segments where data is missing · never fabricates."""
    parts = []
    # Rank movement
    if isinstance(rank_delta, int) and prior_rank not in (None, ""):
        arrow = "↑" if rank_delta < 0 else ("↓" if rank_delta > 0 else "→")
        parts.append(f"Rank {arrow} {prior_rank}→{rank}")
    elif rank:
        parts.append(f"Rank #{rank}")
    # Confidence
    if conf_pct is not None and conf_pct != "":
        parts.append(f"Conf {conf_pct:.0f}%")
    # Momentum
    mom = (ev or {}).get("momentum_direction") if isinstance(ev, dict) else None
    if mom:
        arrow = {"UP": "↑", "STABLE": "→", "DOWN": "↓"}.get(str(mom).upper(), "")
        if arrow:
            parts.append(f"momentum {arrow}")
    # Band drift
    if health_band:
        pretty_band = health_band.replace("_", " ")
        if prior_band and prior_band != health_band.replace(" ", "_"):
            prev_pretty = prior_band.replace("_", " ")
            parts.append(f"band {prev_pretty}→{pretty_band}")
        else:
            parts.append(f"band {pretty_band}")
    # Days remaining
    if isinstance(days_left, int) and days_left > 0:
        parts.append(f"{days_left}d left")
    # Action bit at the end
    if status == "EXIT":
        if ri and ri.get("should_rotate"):
            parts.append(f"→ EXIT (rotate to {ri.get('replacement_ticker') or '?'})")
        else:
            parts.append("→ EXIT")
    elif status == "STRONG BUY":
        parts.append("→ STRONG BUY")
    elif status == "BUY":
        parts.append("→ BUY")
    elif status == "HOLD":
        parts.append("→ HOLD")
    return " · ".join(parts)


def _load_health_card(root: Path, market: str, ticker: str) -> dict | None:
    """Sprint A · look up ticker's Health card from most-recent scoring run.
    Matches on ticker OR short-ticker (health card stores raw ticker like
    TCS.NS · XLSX row uses short TCS · check both)."""
    p = root / "reports" / "research" / f"health_scores_{market}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        short = ticker.replace(".NS", "").replace(".BO", "")
        for c in d.get("cards") or []:
            t = c.get("ticker") or ""
            if t == ticker or t == short \
                or t.replace(".NS", "").replace(".BO", "") == short:
                return c
    except Exception:
        return None
    return None


def _load_alert(root: Path, market: str, ticker: str) -> str:
    """Read profit_protection_{market}.json · return short string per ticker.
    Format: 'CRITICAL · TRIGGER · reason' · blank if no signals for ticker."""
    p = root / "reports" / "research" / f"profit_protection_{market}.json"
    if not p.exists():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        sigs = [s for s in (d.get("signals") or []) if s.get("ticker") == ticker]
        if not sigs:
            return ""
        # Highest severity first · concatenate up to 2
        order = {"critical": 0, "warning": 1, "info": 2}
        sigs.sort(key=lambda s: order.get(s.get("severity", "info"), 3))
        parts = []
        for s in sigs[:2]:
            sev = str(s.get("severity", "info")).upper()
            trig = s.get("trigger", "")
            reason = (s.get("reason") or "")[:40]
            parts.append(f"{sev}·{trig}·{reason}")
        return " || ".join(parts)
    except Exception:
        return ""


def _write_new_workbook(path: Path, rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "AEGIS Daily"
    # Header
    for col_idx, (name, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "D2"      # freeze Date + Country + Run_Type
    # Data
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = LEFT if c_idx <= 6 else RIGHT
        # Row color by Status
        status = row[5]
        if status in STATUS_FILLS:
            ws.cell(row=r_idx, column=6).fill = STATUS_FILLS[status]
    # Auto-filter
    last_col = get_column_letter(len(COLUMNS))
    ws.auto_filter.ref = f"A1:{last_col}{len(rows) + 1}"
    wb.save(path)


def _append_to_workbook(path: Path, rows: list[list]) -> None:
    """Load existing WB · dedup by (Date, Country, Run_Type, Ticker) ·
    replace matching rows with today's · append new ones.

    Schema-migration safe: if the file was written under an older COLUMNS
    spec and the current spec has NEW columns, we rewrite the header row
    and pad existing rows with blank cells for the new columns before
    doing the append. Avoids the 2026-08-04 bug where 3 new columns
    (Prior Rank · Rank Δ · Alert) landed as un-headered data.
    """
    wb = load_workbook(path)
    ws = wb["AEGIS Daily"] if "AEGIS Daily" in wb.sheetnames else wb.active

    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    current_names = [n for (n, _w) in COLUMNS]

    # ── Schema migration · realign old rows to new column positions ──
    # 2026-08-04: added Prior Rank / Rank Δ / Alert between Rank (col 9) and
    # Confidence % (was col 10 · now col 13). Old rows have data at col 10-12
    # (conf/conf_type/model_score) which now belongs at col 13-15 · without
    # migration those values would appear under the wrong column names.
    if headers != current_names:
        # Snapshot old rows keyed by old-header name so we can re-emit them
        # under the new schema · unknown-in-old-headers columns fill blank.
        old_data: list[dict] = []
        for r_idx in range(2, ws.max_row + 1):
            row_map = {headers[c-1]: ws.cell(row=r_idx, column=c).value
                            for c in range(1, len(headers) + 1) if c - 1 < len(headers)}
            old_data.append(row_map)
        # Reset sheet · rewrite header + data under new schema
        ws.delete_rows(1, ws.max_row)
        for col_idx, (name, width) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=name)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = CENTER
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        for r_idx, row_map in enumerate(old_data, start=2):
            for c_idx, (name, _w) in enumerate(COLUMNS, start=1):
                val = row_map.get(name, "")
                if val is not None:
                    cell = ws.cell(row=r_idx, column=c_idx, value=val)
                    cell.alignment = LEFT if c_idx <= 6 else RIGHT
            status = row_map.get("Status")
            if status in STATUS_FILLS:
                ws.cell(row=r_idx, column=6).fill = STATUS_FILLS[status]
        headers = current_names

    key_indices = [headers.index(k) for k in DEDUP_KEY_COLS if k in headers]

    # Existing rows into map keyed by dedup tuple
    existing_map = {}
    for r_idx in range(2, ws.max_row + 1):
        key = tuple(ws.cell(row=r_idx, column=k_idx + 1).value for k_idx in key_indices)
        existing_map[key] = r_idx

    # For each new row · overwrite or append
    for row in rows:
        row_key = tuple(row[k_idx] for k_idx in key_indices)
        target_row = existing_map.get(row_key)
        if target_row is None:
            target_row = ws.max_row + 1
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=target_row, column=c_idx, value=val)
            cell.alignment = LEFT if c_idx <= 6 else RIGHT
        # Row color
        status = row[5]
        if status in STATUS_FILLS:
            ws.cell(row=target_row, column=6).fill = STATUS_FILLS[status]

    # Refresh auto-filter to cover new range
    last_col = get_column_letter(len(COLUMNS))
    ws.auto_filter.ref = f"A1:{last_col}{ws.max_row}"
    wb.save(path)


def build_unified_history(root: Path, asof: str,
                              markets: list[str] | None = None) -> Path:
    """Append today's rows for all markets to reports/telegram/aegis_history.xlsx.

    Returns the path to the unified XLSX (creates if missing · appends
    daily otherwise · dedups by Date+Country+Run_Type+Ticker so same-day
    re-runs update rather than duplicate).
    """
    if markets is None:
        markets = ["india", "usa"]
    out_dir = root / "reports" / "telegram"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "aegis_history.xlsx"

    all_rows = []
    for m in markets:
        all_rows.extend(_collect_rows_for_market(root, m, asof))

    if not path.exists():
        _write_new_workbook(path, all_rows)
    else:
        _append_to_workbook(path, all_rows)

    # Also write today-only snapshot for convenience
    snapshot = out_dir / f"aegis_daily_{asof}.xlsx"
    _write_new_workbook(snapshot, all_rows)

    return path


def build_and_stamp_all(root: Path, asof: str,
                             markets: list[str] | None = None) -> Path:
    """End-to-end refresh (v5 · 2026-08-04):
       1. stamp regime history + rank history for each market
       2. run profit-protection eval (writes profit_protection_{market}.json)
       3. build unified XLSX (which reads the outputs of steps 1-2)

    Safe to call multiple times · all steps are idempotent per (asof, market).
    Preferred entrypoint for scripts/rebuild_xlsx_local.py + telegram sender.
    """
    if markets is None:
        markets = ["india", "usa"]
    from backend.portfolio import rank_history as _rh
    from backend.portfolio import market_regime_stability as _mrs
    from backend.portfolio import profit_protection as _pp
    from backend.portfolio import health_score as _hs
    for m in markets:
        # Stamp regime history
        try:
            _mrs.stamp_today(root, asof, m)
        except Exception as e:
            print(f"[build_and_stamp:{m}] regime stamp skipped · {type(e).__name__}: {e}")
        # Stamp today's ranks + run profit-protection
        recs_path = (root / "usa" / "reports" / "recommendations.json"
                        if m == "usa" else root / "reports" / "recommendations.json")
        if not recs_path.exists():
            continue
        try:
            recs = json.loads(recs_path.read_text(encoding="utf-8")).get("recommendations", [])
            n_stamped = _rh.stamp_today(root, asof, m, "runner2", recs)
            print(f"[build_and_stamp:{m}] rank_history stamped n={n_stamped}")
            signals = _pp.evaluate_all_active(root, m, "runner2", asof, recs)
            _pp.emit_signals(root, m, "runner2", asof, signals)
            print(f"[build_and_stamp:{m}] profit_protection signals={len(signals)}")
            # Sprint A · Health Scores (composite 0-100 per rec)
            hs_payload = _hs.score_all(root, m, recs, asof)
            _hs.emit(root, m, hs_payload)
            print(f"[build_and_stamp:{m}] health_scores n={hs_payload.get('n')} "
                    f"band_changes={hs_payload.get('band_changes')}")
            # Context Intelligence Layer · run composer with 4 adapters
            try:
                from backend.context import composer as _cil
                from backend.context.adapters import DEFAULT_ADAPTERS
                adjustments = [_cil.compose(root, m, asof, r, DEFAULT_ADAPTERS)
                                    for r in recs]
                _cil.emit_run(root, m, asof, adjustments)
                drags = [a.total_drag_pts for a in adjustments]
                n_drag_neg = sum(1 for d in drags if d < -1)
                n_drag_pos = sum(1 for d in drags if d > 1)
                print(f"[build_and_stamp:{m}] CIL n={len(adjustments)} "
                        f"negative-drag={n_drag_neg} positive-boost={n_drag_pos}")
            except Exception as e:
                print(f"[build_and_stamp:{m}] CIL failed · {type(e).__name__}: {e}")
            # Economic Calendar · daily ingest (data-only · Phase 2 prep)
            try:
                from backend.context.economic_calendar import ingest as _ec
                summary = _ec.ingest_daily(root, asof)
                print(f"[build_and_stamp:{m}] economic_calendar appended={summary['total_appended']}")
            except Exception as e:
                print(f"[build_and_stamp:{m}] economic_calendar failed · {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[build_and_stamp:{m}] pp/rank skipped · {type(e).__name__}: {e}")
    return build_unified_history(root, asof, markets=markets)


def maybe_sync_google_sheet(xlsx_path: Path) -> tuple[bool, str]:
    """Mirror XLSX to Google Sheets IF creds env vars set. No-op otherwise."""
    creds_json = os.environ.get("GSHEETS_CREDS_JSON")
    sheet_id = os.environ.get("GSHEETS_SHEET_ID")
    if not creds_json or not sheet_id:
        return False, "GSHEETS_CREDS_JSON + GSHEETS_SHEET_ID not set · skipped"
    if not Path(creds_json).exists():
        return False, f"creds file missing: {creds_json}"
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return False, "install missing: pip install gspread google-auth"
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(creds_json, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    wb = load_workbook(xlsx_path, read_only=True)
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        try:
            existing = sh.worksheet(sheet_name)
            existing.clear()
        except gspread.WorksheetNotFound:
            existing = sh.add_worksheet(title=sheet_name, rows=200, cols=40)
        rows = [[c.value for c in row] for row in ws.iter_rows()]
        if rows:
            existing.update("A1", rows, value_input_option="USER_ENTERED")
    return True, f"synced {len(wb.sheetnames)} sheets to google_sheet={sheet_id}"
