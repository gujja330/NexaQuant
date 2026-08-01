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


# Column schema · every field from AEGIS_STOCK_CARD_FORMAT.md
# Date + Country + Run_Type + Ticker = dedup key (first 4 columns · frozen)
COLUMNS = [
    ("Date",                12),
    ("Country",             10),
    ("Run_Type",            10),      # "R1" | "R2"
    ("Ticker",              12),
    ("Company",             22),
    ("Status",              12),
    ("Rank",                6),
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
    ("Current Perf %",      15),
    ("Max Gain %",          12),
    ("Max DD %",            11),
    ("Lifecycle State",     16),
    ("Exit Triggers Hit",   22),
    ("Top Drivers",         32),
    ("Risk Flags",          28),      # NEW · e.g. "Earnings in 5d, High Beta"
    ("Sector",              20),
    ("Sector Exposure %",   17),      # NEW · portfolio-level sum for this sector
    ("Portfolio Weight %",  18),
    ("Expected Alpha %",    17),
    ("Confidence Band Low %",  20),   # NEW · alpha - σ
    ("Confidence Band High %", 21),   # NEW · alpha + σ
    ("Correlation",         12),
    ("Hist Win Rate %",     15),
    ("Hist Median Ret %",   17),
    ("Hist Avg Hold (d)",   18),
    ("Last Updated (UTC)",  20),
]

DEDUP_KEY_COLS = ["Date", "Country", "Run_Type", "Ticker"]

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
STATUS_FILLS = {
    "STRONG BUY":  PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid"),
    "NEW BUY":     PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
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
    if ri.get("should_rotate"):
        status = "ROTATE OUT"
    elif entry_action == "BUY" and pct_action == "STRONG_BUY":
        status = "STRONG BUY"
    elif entry_action == "BUY":
        status = "NEW BUY"
    elif entry_action == "SELL" or ia.get("if_holding") in ("EXIT", "REDUCE", "SELL"):
        status = "EXIT"
    else:
        status = "HOLD"

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

    stop = ez.get("stop_loss")
    t1 = ez.get("target_1")
    t2 = ez.get("target_2")
    if t2 is None and t1 is not None and current_price:
        t2 = current_price + (t1 - current_price) * 1.5

    base_for_pct = entry_price or current_price
    risk_pct = _pct_from_range(base_for_pct, stop)
    t1_pct = _pct_from_range(base_for_pct, t1)
    t2_pct = _pct_from_range(base_for_pct, t2)

    cur_ret = round((current_price / entry_price - 1) * 100, 2) if (entry_price and current_price) else None
    max_gain = round((high_water / entry_price - 1) * 100, 2) if (entry_price and high_water) else None
    max_dd = round((low_water / entry_price - 1) * 100, 2) if (entry_price and low_water) else None

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

    # Risk Flags · deferred to R007 (needs earnings calendar + beta + sector overweight detector)
    risk_flags = ""

    # Sector Exposure · portfolio-level sum · deferred to R007 (needs cross-position aggregation)
    sector_exposure = ""

    # Confidence Band · deferred to R007 (needs per-setup calibration variance σ)
    conf_low = ""
    conf_high = ""

    return [
        asof, country, runner, ticker, company, status,
        rank if rank else "",
        conf_pct if conf_pct is not None else "",
        conf_type,
        model_score if model_score is not None else "",
        days_rec if days_rec else "",
        horizon if horizon else "",
        days_left if days_left is not None else "",
        first_seen if first_seen else "",
        current_price if current_price else "",
        entry_price if entry_price else "",
        ez.get("ideal_buy_low") if ez.get("ideal_buy_low") else "",
        ez.get("ideal_buy_high") if ez.get("ideal_buy_high") else "",
        stop if stop else "",
        round(risk_pct, 2) if risk_pct is not None else "",
        t1 if t1 else "",
        round(t1_pct, 2) if t1_pct is not None else "",
        t2 if t2 else "",
        round(t2_pct, 2) if t2_pct is not None else "",
        cur_ret if cur_ret is not None else "",
        max_gain if max_gain is not None else "",
        max_dd if max_dd is not None else "",
        state,
        triggers_str,
        drivers_str,
        risk_flags,          # NEW · R007
        sector,
        sector_exposure,     # NEW · R007
        alloc if alloc else "",
        round(exp_alpha, 2) if exp_alpha is not None else "",
        conf_low,            # NEW · R007
        conf_high,           # NEW · R007
        "",  # Correlation · R007
        "",  # Hist Win Rate · R007
        "",  # Hist Median Ret · R007
        "",  # Hist Avg Hold · R007
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
        for o in (rv.get("runner1_orphans") or []):
            r1_rec = _r1_orphan_to_rec_shape(o, market)
            rows.append(_rec_to_row(r1_rec, market, root, runner="R1", asof=asof))
    return rows


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
    replace matching rows with today's · append new ones."""
    wb = load_workbook(path)
    ws = wb["AEGIS Daily"] if "AEGIS Daily" in wb.sheetnames else wb.active

    # Build header index
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
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
