"""Emit a provenance companion JSONL for each market's XLSX.

For every Portfolio row + Exit-History row currently visible in the
production XLSX, resolve the (Ticker, Runner, entry_date) tuple to a
canonical Position ID by joining against the AEGIS History sheet and
the Registry. Emit one record per row with the full provenance:

    { position_id, legacy_position_id, ticker, runner, entry_date,
      exit_date, lifecycle, population, asof, source, engine, sheet }

Output:
    reports/telegram/aegis_history_{market}_provenance.jsonl

The reconciler can consume this file to enforce provenance without
requiring the XLSX itself to change layout. CEO 2026-09-01.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date
from pathlib import Path
from openpyxl import load_workbook

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research import opportunity_registry as oreg


def _col(hdr, name):
    for i, c in enumerate(hdr):
        if c and name.lower() == str(c).lower(): return i
    return None


def _col_any(hdr, *names):
    """Return the first matching column index for any of the given header
    names. Handles the c=0 case correctly (0 is a valid index · falsy in
    Python · so `_col(...) or _col(...)` would silently miss column A)."""
    for n in names:
        i = _col(hdr, n)
        if i is not None:
            return i
    return None


def _find_hdr_row(rows):
    for i, r in enumerate(rows[:8]):
        if r and sum(1 for c in r if c is not None) >= 5:
            return i
    return 0


def emit(market: str, root: Path) -> dict:
    market_l = market.lower()
    xlsx = root / "reports" / "telegram" / f"aegis_history_{market_l}.xlsx"
    if not xlsx.exists():
        return {"error": f"artifact not present · {xlsx}", "n": 0}
    wb = load_workbook(xlsx, read_only=True, data_only=True)
    asof = date.today().isoformat()
    out_records: list[dict] = []

    # Load Registry index (ticker, runner, entry_date) -> Position ID
    reg = oreg.load_all(root)
    reg_by_key: dict[tuple, str] = {}
    reg_legacy_by_key: dict[tuple, str] = {}
    for _pid, opps in reg.items():
        for o in opps:
            if o.market.lower() != market_l: continue
            tk = str(o.ticker or "").split(".", 1)[0].upper()
            rn = str(o.runner or "").upper()
            ed = str(o.created_date or "")[:10]
            key = (tk, rn, ed)
            reg_by_key[key] = o.opportunity_id
            reg_legacy_by_key[key] = getattr(o, "legacy_position_id", "") or ""

    # Also build a lookup from AEGIS History (has PID column already)
    hist_sheet = f"AEGIS {market.upper()} History"
    hist_by_key: dict[tuple, str] = {}
    hist_legacy_by_key: dict[tuple, str] = {}
    if hist_sheet in wb.sheetnames:
        ws_h = wb[hist_sheet]
        rows_h = list(ws_h.iter_rows(values_only=True))
        hdr_h = rows_h[0]
        c_pid = _col(hdr_h, "Position ID")
        c_legacy = _col(hdr_h, "Legacy Position ID")
        c_tk = _col(hdr_h, "Ticker")
        c_run = _col_any(hdr_h, "Run_Type", "Runner")
        c_rec = _col(hdr_h, "Recommended")
        for r in rows_h[1:]:
            if not r or c_pid is None or not r[c_pid]: continue
            tk = str(r[c_tk] or "").split(".", 1)[0].upper() if c_tk is not None else ""
            rn = str(r[c_run] or "").upper() if c_run is not None else ""
            ed = str(r[c_rec] or "")[:10] if c_rec is not None else ""
            key = (tk, rn, ed)
            if key not in hist_by_key:
                hist_by_key[key] = str(r[c_pid])
            if c_legacy is not None and r[c_legacy] and key not in hist_legacy_by_key:
                hist_legacy_by_key[key] = str(r[c_legacy])

    def _resolve_pid(tk: str, rn: str, ed: str) -> tuple[str, str]:
        key = (tk, rn, ed)
        pid = reg_by_key.get(key) or hist_by_key.get(key) or ""
        legacy = reg_legacy_by_key.get(key) or hist_legacy_by_key.get(key) or ""
        return pid, legacy

    # ── R2 production holdings ─────────────────────────────────────
    # CEO 2026-09-07 · FIVE-SHEET spec. Read by HEADER NAME through the
    # shared reader: this script previously addressed 01_Portfolio by
    # column index and, once the layout changed, emitted 0 records without
    # raising · a silent zero that looks exactly like a clean run.
    from backend.delivery import five_sheet_reader as _fsr

    if _fsr.SHEET_R2 in wb.sheetnames:
        for rec in _fsr.r2_positions(wb):
            tk = str(rec.get("Stock") or "").split(".", 1)[0].upper()
            ed = str(rec.get("Entry Date") or "")[:10]
            if ed == "—":
                ed = ""
            pid = str(rec.get("Position ID") or "")
            _rp, legacy = _resolve_pid(tk, "R2", ed)
            out_records.append({
                "sheet": _fsr.SHEET_R2,
                "position_id": pid or _rp,
                "legacy_position_id": legacy,
                "ticker": tk,
                "runner": "R2",
                "entry_date": ed,
                "exit_date": "",
                "lifecycle": "ACTIVE",
                "population": "CURRENT_HOLDING",
                "asof": asof,
                "source": "build_aegis_3sheet_workbook",
                "engine": "aegis_canonical_v3",
            })

    # ── R1 advisory holdings ───────────────────────────────────────
    # R1 is advisory and never enters production P&L · it is recorded here
    # with population ADVISORY so provenance is complete without letting
    # an R1 row be mistaken for a production holding.
    if _fsr.SHEET_R1 in wb.sheetnames:
        for rec in _fsr.r1_positions(wb):
            tk = str(rec.get("Stock") or "").split(".", 1)[0].upper()
            ed = str(rec.get("Entry Date") or "")[:10]
            if ed == "—":
                ed = ""
            pid = str(rec.get("Position ID") or "")
            _rp, legacy = _resolve_pid(tk, "R1", ed)
            out_records.append({
                "sheet": _fsr.SHEET_R1,
                "position_id": pid if pid.upper().startswith(("USA-", "IND-")) else _rp,
                "legacy_position_id": legacy,
                "ticker": tk,
                "runner": "R1",
                "entry_date": ed,
                "exit_date": "",
                "lifecycle": "ACTIVE",
                "population": "ADVISORY",
                "asof": asof,
                "source": "build_aegis_3sheet_workbook",
                "engine": "aegis_canonical_v3",
            })

    # ── EXIT · unified realized exits (R1 · R2 · Momentum) ─────────
    if _fsr.SHEET_EXIT in wb.sheetnames:
        for rec in _fsr.exits(wb):
            pid = str(rec.get("Position ID") or "")
            if not pid.upper().startswith(("USA-", "IND-")):
                continue
            tk = str(rec.get("Stock") or "").split(".", 1)[0].upper()
            src = str(rec.get("Source") or "").upper()
            rn = "R1" if src.startswith("R1") else ("R2" if src == "R2" else src)
            ed = str(rec.get("Entry Date") or "")[:10]
            xd = str(rec.get("Exit Date") or "")[:10]
            if ed == "—":
                ed = ""
            if xd == "—":
                xd = ""
            legacy = reg_legacy_by_key.get((tk, rn, ed), "")
            out_records.append({
                "sheet": _fsr.SHEET_EXIT,
                "position_id": pid,
                "legacy_position_id": legacy,
                "ticker": tk,
                "runner": rn,
                "entry_date": ed,
                "exit_date": xd,
                "lifecycle": "CLOSED",
                "population": ("ADVISORY" if rn == "R1"
                               else str(rec.get("Classification") or
                                        "HISTORICAL_EXIT").upper()),
                "asof": asof,
                "source": "build_aegis_3sheet_workbook",
                "engine": "aegis_canonical_v3",
            })

    out_path = root / "reports" / "telegram" / f"aegis_history_{market_l}_provenance.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for rec in out_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Coverage summary
    n = len(out_records)
    n_pid = sum(1 for r in out_records if r["position_id"])
    n_no_pid = n - n_pid
    return {
        "market": market_l,
        "n_records": n,
        "n_with_position_id": n_pid,
        "n_missing_position_id": n_no_pid,
        "coverage_pct": round(n_pid / max(1, n) * 100, 1),
        "out_path": str(out_path.relative_to(root)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                     default="both")
    args = ap.parse_args()
    markets = ["india", "usa"] if args.market == "both" else [args.market]
    for m in markets:
        rep = emit(m, _ROOT)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
