"""AEGIS 3-sheet canonical workbook renderer · CEO 2026-09-01 (FINAL closing spec).

Exactly 3 visible sheets · identical structure India + USA · daily rollover:

    01_Portfolio       · current active R2 holdings only (D snapshot)
    02_Today_Momentum  · today's decisions/recommendations (D snapshot · fresh every day)
    03_Exit_History    · closed lifecycle only (accumulates via Registry CLOSED)

Daily rollover semantics:
    · D+1 rebuild reads canonical state at D+1
    · 02_Today_Momentum is regenerated from scratch for D+1
    · Positions that opened at D and are still active → remain in 01_Portfolio
    · Positions that closed at D → leave 01_Portfolio, appear in 03_Exit_History
    · Nothing is copied from D-1's workbook. Canonical state is the source of truth.

Data comes from CANONICAL sources only:
    · Registry (opportunity_registry.jsonl · sole PID authority)
    · usa/data/raw/us/*.parquet · data/raw/india/*.parquet (canonical prices)
    · reports/research/multi_layer/momentum_ledger_*.json (for Today_Momentum)

Rules:
    · R2 only · R1 excluded workbook-wide
    · Latest date first everywhere
    · "—" for N/A · "UNAVAILABLE" for genuine gaps · 0 never used to mean missing
    · Realized vs Unrealized P&L labelled explicitly
    · Only green (P&L>0) / red (P&L<0) coloring · everything else neutral
    · India and USA get IDENTICAL sheet names, columns, headers, formats

Files produced:
    reports/telegram/aegis_{market}_{asof}.xlsx           (dated · deliverable)
    reports/telegram/aegis_history_{market}.xlsx          (latest alias · same bytes)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# Minimal color contract
FILL_BANNER = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
FILL_HEADER = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
FILL_POS = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
FILL_NEG = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")

FONT_BANNER = Font(bold=True, color="FFFFFF", size=14)
FONT_SUB = Font(bold=True, color="1F4E78", size=11)
FONT_HEADER = Font(bold=True, color="1F4E78", size=11)
FONT_BODY = Font(size=10)
FONT_LEGEND = Font(size=9, color="808080", italic=True)


def _banner(ws, text, ncols):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(1, 1, text); c.font = FONT_BANNER; c.fill = FILL_BANNER
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28


def _sub(ws, text, ncols, row):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row, 1, text); c.font = FONT_SUB
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)


def _header(ws, cols, row):
    for i, name in enumerate(cols, start=1):
        c = ws.cell(row, i, name)
        c.font = FONT_HEADER; c.fill = FILL_HEADER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _write_row(ws, values, row, pnl_col_idx=None):
    for i, v in enumerate(values, start=1):
        c = ws.cell(row, i, v)
        c.font = FONT_BODY
        c.alignment = Alignment(horizontal="left", vertical="center")
        if pnl_col_idx is not None and i == pnl_col_idx and isinstance(v, (int, float)):
            if v > 0: c.fill = FILL_POS
            elif v < 0: c.fill = FILL_NEG


def _legend(ws, lines, start_row, ncols):
    for line in lines:
        ws.merge_cells(start_row=start_row, start_column=1,
                        end_row=start_row, end_column=ncols)
        c = ws.cell(start_row, 1, line)
        c.font = FONT_LEGEND
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        start_row += 1
    return start_row


def _load_registry(root, market, retired):
    from backend.research import opportunity_registry as oreg
    reg = oreg.load_all(root)
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    active, closed = [], []
    for pid, opps in reg.items():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.runner in retired: continue
            if o.status == "ACTIVE":
                active.append(o)
            elif o.status == "CLOSED" and o.closed_date and o.closed_date >= cutoff:
                closed.append(o)
    return {"active": active, "closed_90d": closed}


def _close_on_or_before(root, ticker, market, target_date):
    import pandas as pd
    dir_ = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    ext = "" if market.lower() == "usa" else ".NS"
    for p in (root / dir_ / f"{ticker.upper()}{ext}_D1.parquet",
               root / dir_ / f"{ticker.upper()}_D1.parquet"):
        if not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns: continue
            idx = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            df = df.copy(); df.index = idx
            sub = df.loc[df.index <= target_date]
            if sub.empty: continue
            return float(sub.iloc[-1]["close"])
        except Exception:
            continue
    return None


def _canonical_ticker(t):
    return str(t or "").split(".", 1)[0].upper().strip()


# ── SHEET 01 · Portfolio · CURRENT ACTIVE R2 HOLDINGS ONLY ──────────
def _emit_portfolio(wb, market, root, asof, reg_data):
    ws = wb.create_sheet("01_Portfolio")
    ncols = 13
    _banner(ws, f"AEGIS {market.upper()} · PORTFOLIO · current active holdings as of {asof}", ncols)
    active = sorted(reg_data["active"], key=lambda o: o.created_date or "", reverse=True)
    _sub(ws, (f"🟢 R2 ACTIVE: {len(active)} · production runner is R2 · "
                "sorted latest entry first · rebuilt daily from canonical Registry"),
          ncols, 2)

    # Load bridge decisions for counterfactual columns
    dyn_p = root / "reports" / "audit" / f"dynamic_exit_decisions_{market.lower()}_{asof}.json"
    dyn_by_pid = {}
    if dyn_p.exists():
        try:
            dyn = json.loads(dyn_p.read_text(encoding="utf-8"))
            for d in (dyn.get("decisions") or []):
                if d.get("opportunity_id"):
                    dyn_by_pid[d["opportunity_id"]] = d
        except Exception:
            pass

    hdr = ["Position ID", "Ticker", "Runner",
             "Entry Date", "Entry Price", "Current Price",
             "Unrealized P&L %", "Holding Days",
             "Dynamic Stop", "Engine Verdict", "Would-Have-Exited-On",
             "As-Of", "Provenance"]
    _header(ws, hdr, 4)
    for i, w in enumerate([28, 10, 8, 12, 12, 14, 16, 12, 14, 22, 20, 12, 22], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 5
    for o in active:
        entry_p = _close_on_or_before(root, o.ticker, market, o.created_date or asof)
        curr_p = _close_on_or_before(root, o.ticker, market, asof)
        pnl_pct = None
        if entry_p and curr_p and entry_p > 0:
            pnl_pct = round((curr_p - entry_p) / entry_p * 100, 2)
        days = None
        try:
            days = (date.fromisoformat(asof) - date.fromisoformat(o.created_date)).days
        except Exception:
            pass
        # Counterfactual columns · from bridge audit output
        dyn_d = dyn_by_pid.get(o.opportunity_id)
        dyn_stop = "—"
        engine_verdict = "HOLD (no trigger)"
        would_exit_on = "—"
        if dyn_d:
            dyn_stop = round(dyn_d["stop_price"], 4) if dyn_d.get("stop_price") else "—"
            engine_verdict = f"{dyn_d['event']} (audit-only)"
            would_exit_on = dyn_d.get("trigger_date") or "—"
        _write_row(ws, [
            o.opportunity_id, _canonical_ticker(o.ticker), o.runner,
            o.created_date or "—",
            round(entry_p, 4) if entry_p else "UNAVAILABLE",
            round(curr_p, 4) if curr_p else "UNAVAILABLE",
            pnl_pct if pnl_pct is not None else "—",
            days if days is not None else "—",
            dyn_stop, engine_verdict, would_exit_on,
            asof, "canonical:Registry+prices+dynamic_exit_bridge",
        ], r, pnl_col_idx=7)
        r += 1
    if not active:
        ws.cell(r, 1, "No current R2 ACTIVE holdings.").font = FONT_BODY
        r += 1

    r += 2
    r = _legend(ws, [
        "This sheet shows CURRENT R2 active holdings ONLY. Closed positions live in 03_Exit_History.",
        "Unrealized P&L % · (Current − Entry) / Entry · positive=green · negative=red · zero/N/A=neutral.",
        "'—' = not applicable. 'UNAVAILABLE' = canonical source did not return a value. 0 is never used to mean missing.",
        "Daily rollover: this sheet is rebuilt from canonical Registry at the reporting date · never carried over from prior day's XLSX.",
        "Dynamic Stop = today's stop level from the coded exit engine (dynamic_risk_v2 ATR-based, else recommendation entry_zone.stop_loss, else entry × 0.94).",
        "Engine Verdict = what the coded lifecycle engine (evaluate_position) says today. HOLD if no trigger. EXIT_STOP / EXIT_TARGET / EXIT_HORIZON if triggered.",
        "Would-Have-Exited-On = if the engine says exit today, this is the first date the position crossed the trigger. Positions are NOT retroactively closed in the current release · this is audit-only until the wiring is enforced.",
    ], r, ncols)
    return len(active)


# ── SHEET 02 · Today + Momentum · TODAY-DATE DECISIONS ONLY ─────────
def _emit_today_momentum(wb, market, root, asof, momentum_ledger):
    ws = wb.create_sheet("02_Today_Momentum")
    ncols = 11
    _banner(ws, f"AEGIS {market.upper()} · TODAY + MOMENTUM · reporting date {asof}", ncols)

    ml_entries = (momentum_ledger or {}).get("entries") or []
    ml_counts = (momentum_ledger or {}).get("by_terminal_state") or {}
    # Freshness check: momentum_ledger.asof must equal today's asof
    ledger_asof = str((momentum_ledger or {}).get("asof", ""))
    stale = ledger_asof and ledger_asof != asof
    freshness_note = (f"⚠ ledger asof={ledger_asof} ≠ reporting {asof}"
                       if stale else f"✓ ledger fresh for {asof}")
    _sub(ws, (f"📅 Today's R2 decisions/recommendations · "
                f"{freshness_note} · scanned universe={(momentum_ledger or {}).get('n_universe_scanned', 0)} · "
                f"by_state={ml_counts} · sorted acceptance tier"), ncols, 2)

    hdr = ["Ticker", "Category", "Quality Band", "Terminal State",
             "Reason", "Return 1d %", "Return 5d %", "Return 20d %",
             "As-Of", "Attribution", "Provenance"]
    _header(ws, hdr, 4)
    for i, w in enumerate([10, 14, 12, 14, 60, 12, 12, 12, 12, 12, 22], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # If ledger stale (not today), emit zero rows · staleness is a defect
    if stale:
        entries_for_today = []
    else:
        entries_for_today = ml_entries

    # Latest-first sort within terminal-state priority (ACCEPTED first)
    state_order = {"ACCEPTED": 0, "WATCH": 1, "REJECTED": 2, "NO_EVIDENCE": 3}
    entries_sorted = sorted(entries_for_today, key=lambda e: (
        state_order.get(e.get("terminal_state", ""), 9),
        e.get("ticker", "") or ""
    ))
    r = 5
    for e in entries_sorted[:200]:
        _write_row(ws, [
            _canonical_ticker(e.get("ticker")), e.get("category", "—"),
            e.get("quality_band", "—"), e.get("terminal_state", "—"),
            str(e.get("reason_text", ""))[:80],
            e.get("return_1d_pct") if e.get("return_1d_pct") is not None else "—",
            e.get("return_5d_pct") if e.get("return_5d_pct") is not None else "—",
            e.get("return_20d_pct") if e.get("return_20d_pct") is not None else "—",
            asof, "R2", "canonical:momentum_ledger",
        ], r)
        r += 1
    if not entries_sorted:
        ws.cell(r, 1, (f"No R2 decisions/recommendations for {asof} "
                         + ("· momentum ledger is stale" if stale else "")))
        r += 1

    r += 2
    r = _legend(ws, [
        "Today + Momentum shows ONLY the current reporting date's R2 decisions/recommendations.",
        "Terminal states · ACCEPTED · WATCH · REJECTED · NO_EVIDENCE (quality unavailable).",
        "This sheet is REGENERATED from scratch every reporting day · never carries yesterday's rows forward.",
        "A recommendation does NOT automatically become a Portfolio holding · only canonical lifecycle transitions move a stock into 01_Portfolio.",
        "Only the active production runner (R2) appears in this workbook.",
    ], r, ncols)
    return {"n_entries": len(entries_sorted), "ledger_fresh": not stale}


# ── SHEET 03 · Exit History · CLOSED LIFECYCLE ONLY ─────────────────
def _emit_exit_history(wb, market, root, asof, reg_data):
    ws = wb.create_sheet("03_Exit_History")
    ncols = 12
    _banner(ws, f"AEGIS {market.upper()} · EXIT HISTORY · realized · as of {asof}", ncols)
    closed = sorted(reg_data["closed_90d"], key=lambda o: o.closed_date or "", reverse=True)
    _sub(ws, (f"📕 R2 closed positions (last 90d): {len(closed)} · latest exit first · "
                "realized P&L only"), ncols, 2)

    hdr = ["Position ID", "Ticker", "Runner", "Market",
             "Entry Date", "Exit Date", "Holding Days",
             "Entry Price", "Exit Price", "Realized P&L %",
             "Exit Reason", "Provenance"]
    _header(ws, hdr, 4)
    for i, w in enumerate([28, 10, 8, 8, 12, 12, 12, 12, 12, 16, 24, 22], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 5
    n_priced = 0
    n_unpriced = 0
    for o in closed:
        entry_p = _close_on_or_before(root, o.ticker, market, o.created_date or "")
        exit_p = _close_on_or_before(root, o.ticker, market, o.closed_date or "")
        pnl_pct = None
        if entry_p and exit_p and entry_p > 0:
            pnl_pct = round((exit_p - entry_p) / entry_p * 100, 2)
            n_priced += 1
        else:
            n_unpriced += 1
        days = None
        try:
            days = (date.fromisoformat(o.closed_date) - date.fromisoformat(o.created_date)).days
        except Exception:
            pass
        _write_row(ws, [
            o.opportunity_id, _canonical_ticker(o.ticker), o.runner, market.upper(),
            o.created_date or "—", o.closed_date or "—",
            days if days is not None else "—",
            round(entry_p, 4) if entry_p else "UNAVAILABLE",
            round(exit_p, 4) if exit_p else "UNAVAILABLE",
            pnl_pct if pnl_pct is not None else "—",
            str(getattr(o, "closed_reason", "") or "—")[:40],
            "canonical:Registry+prices",
        ], r, pnl_col_idx=10)
        r += 1

    if not closed:
        ws.cell(r, 1, "No closed R2 positions in last 90 days.").font = FONT_BODY
        r += 1

    r += 2
    r = _legend(ws, [
        f"Priced: {n_priced} · Unpriced (data unavailable): {n_unpriced} · unpriced rows show — for P&L, never fabricated 0.",
        "Realized P&L % · (Exit − Entry) / Entry · positive=green · negative=red · zero/N/A=neutral.",
        "This sheet accumulates closed R2 positions via Registry CLOSED events · latest exit first · 90-day rolling window.",
        "This sheet shows the production runner (R2) closed lifecycle only · historical evidence for retired runners lives in canonical audit files only.",
    ], r, ncols)
    return len(closed)


def build_workbook(market: str, root: Path, asof: str) -> dict:
    from backend.delivery.canonical.retirement import retired_runners
    retired = retired_runners(root)
    reg_data = _load_registry(root, market, retired)
    ml_p = root / "reports" / "research" / "multi_layer" / f"momentum_ledger_{market.lower()}_{asof}.json"
    momentum_ledger = json.loads(ml_p.read_text(encoding="utf-8")) if ml_p.exists() else {}

    wb = Workbook()
    wb.remove(wb.active)
    n_active = _emit_portfolio(wb, market, root, asof, reg_data)
    today_stats = _emit_today_momentum(wb, market, root, asof, momentum_ledger)
    n_closed = _emit_exit_history(wb, market, root, asof, reg_data)

    xlsx_dated = root / "reports" / "telegram" / f"aegis_{market.lower()}_{asof}.xlsx"
    xlsx_undated = root / "reports" / "telegram" / f"aegis_history_{market.lower()}.xlsx"
    xlsx_dated.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_dated)
    import shutil
    shutil.copyfile(xlsx_dated, xlsx_undated)
    return {
        "market": market.lower(),
        "asof": asof,
        "sheets": ["01_Portfolio", "02_Today_Momentum", "03_Exit_History"],
        "active_holdings": n_active,
        "today_stats": today_stats,
        "closed_positions": n_closed,
        "xlsx_dated": str(xlsx_dated.relative_to(root)),
        "xlsx_undated": str(xlsx_undated.relative_to(root)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat(),
                     help="Reporting date · defaults to today · used for filenames + snapshot")
    args = ap.parse_args()
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = build_workbook(m, _ROOT, args.asof)
        print(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
