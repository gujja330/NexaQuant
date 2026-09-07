"""AEGIS · shared reader for the five-sheet workbook · CEO 2026-09-07.

Every downstream consumer (reconciler, provenance companion, overlap
classifier, visual sign-off) reads the delivered workbook through this
module.

WHY THIS EXISTS
---------------
The consumers used to address the workbook by SHEET NAME and COLUMN INDEX ·
indexing a legacy sheet by hard-coded ordinal to find the Position ID.
When the layout changed to five sheets, two of them crashed and two
silently produced zero records ·
`emit_provenance_companion` wrote 0 rows and
`portfolio_exit_overlap_classifier` reported "tickers=0 defects=0", which
reads exactly like a clean run. Silent zeros are the failure mode this
whole correction batch exists to eliminate.

Addressing columns by HEADER NAME means a column can move without breaking
a consumer, and a column that genuinely disappears raises instead of
yielding None.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional

SHEET_R1 = "R1"
SHEET_R2 = "R2"
SHEET_MOMENTUM = "MOMENTUM"
SHEET_DAILY = "DAILY RECOMMENDATION"
SHEET_EXIT = "EXIT"
FIVE_SHEETS = [SHEET_R1, SHEET_R2, SHEET_MOMENTUM, SHEET_DAILY, SHEET_EXIT]

# Legacy name -> current sheet, for consumers being migrated.
LEGACY_MAP = {
    "01_Portfolio": SHEET_R2,
    "01_Investments": SHEET_DAILY,
    "02_Today_Momentum": SHEET_MOMENTUM,
    "03_Exit_History": SHEET_EXIT,
    "05_R1_Advisory": SHEET_R1,
}


class SheetMissing(KeyError):
    """Raised instead of returning nothing · a missing sheet is loud."""


def load(path: Path, read_only: bool = True):
    from openpyxl import load_workbook
    return load_workbook(path, read_only=read_only, data_only=True)


def _values(ws) -> list:
    return [[c for c in row] for row in ws.iter_rows(values_only=True)]


def find_header(rows: list, must_have: list) -> tuple:
    """Locate the header row containing every label in `must_have`.

    Returns (index, header_list) · (-1, []) when absent. Sheets carry
    banners and section sub-headings above the real header, so the header
    is found by content, never by a fixed row number.
    """
    for i, r in enumerate(rows):
        cells = {str(c).strip() for c in r if c is not None}
        if all(m in cells for m in must_have):
            return i, list(r)
    return -1, []


def records(wb, sheet: str, must_have: list,
            stop_on_blank: bool = True) -> Iterator[dict]:
    """Yield body rows of `sheet` as {header_name: value} dicts.

    Stops at the legend/summary block below the data · those rows also
    occupy column A and would otherwise be emitted as if they were records.
    """
    if sheet not in wb.sheetnames:
        raise SheetMissing(
            "sheet %r not in workbook %s" % (sheet, wb.sheetnames))
    rows = _values(wb[sheet])
    hi, hdr = find_header(rows, must_have)
    if hi < 0:
        raise SheetMissing(
            "header %s not found on sheet %r" % (must_have, sheet))
    names = [str(c).strip() if c is not None else "" for c in hdr]
    first = names[0]
    for r in rows[hi + 1:]:
        if all(c is None or str(c).strip() == "" for c in r):
            if stop_on_blank:
                continue
            break
        rec = {}
        for i, n in enumerate(names):
            if n:
                rec[n] = r[i] if i < len(r) else None
        # Legend prose is long free text in column A under a header whose
        # first column holds a short identifier. Treat it as end-of-data.
        v0 = rec.get(first)
        if isinstance(v0, str) and len(v0) > 40:
            break
        if v0 is None or str(v0).strip() == "":
            continue
        # A body row fills EVERY requested column. Sheets carry further
        # sections below the data (the Momentum->R2 reconciliation table on
        # DAILY RECOMMENDATION, the monthly summary on EXIT) whose narrower
        # rows would otherwise be yielded as if they were records · that is
        # how a reconciliation stage could be counted as a recommendation.
        if any(rec.get(k) is None or str(rec.get(k)).strip() == ""
               for k in must_have):
            break
        yield rec


def r2_positions(wb) -> list:
    """Current R2 production holdings · the successor to 01_Portfolio."""
    return list(records(wb, SHEET_R2,
                        ["Stock", "Dynamic Stop", "Action", "Position ID"]))


def r1_positions(wb) -> list:
    """R1 advisory holdings · advisory only · never production P&L."""
    return list(records(wb, SHEET_R1,
                        ["Stock", "Review State", "Action"]))


def exits(wb) -> list:
    """Unified exit history · R1 · R2 · Momentum."""
    return list(records(wb, SHEET_EXIT,
                        ["Source", "Stock", "Realized P&L %", "Position ID"]))


def production_exits(wb) -> list:
    """R2 production exits only · excludes R1 advisory and administrative.

    This is the population that may enter production P&L. Keeping the
    filter here means no consumer can accidentally count an R1 advisory
    exit as a production result.
    """
    return [e for e in exits(wb)
            if str(e.get("Source", "")).strip() == "R2"
            and str(e.get("Classification", "")).strip() == "production"]


def r2_production_trades(wb) -> list:
    """Closed R2 PRODUCTION trades in a normalised research shape.

    Used by the multi-layer research consumers (stress-regime,
    crash-resilience) which previously each re-derived this from
    hard-coded column ordinals on the old exit sheet. Advisory (R1) and
    administrative rows are excluded here so a research population can
    never silently include them.

    Returns [{ticker, sector, entry_date, exit_date, pnl_pct, days}]
    """
    from datetime import date as _d
    out = []
    for r in production_exits(wb):
        ed = str(r.get("Entry Date") or "")[:10]
        xd = str(r.get("Exit Date") or "")[:10]
        if ed == "—":
            ed = ""
        if xd == "—":
            xd = ""
        try:
            pnl = r.get("Realized P&L %")
            pnl = 0.0 if pnl in (None, "", "—") else float(pnl)
        except (TypeError, ValueError):
            pnl = 0.0
        days = r.get("Holding Days")
        try:
            days = int(days)
        except (TypeError, ValueError):
            try:
                days = (_d.fromisoformat(xd) - _d.fromisoformat(ed)).days
            except Exception:
                days = 0
        out.append({
            "ticker": str(r.get("Stock") or "").upper().split(".", 1)[0],
            "sector": str(r.get("Sector") or ""),
            "entry_date": ed, "exit_date": xd,
            "pnl_pct": round(pnl, 4), "days": days,
        })
    return out


def daily_rows(wb) -> list:
    return list(records(wb, SHEET_DAILY,
                        ["Source", "Stock", "Status", "Action"]))


def asof_of(wb, sheet: str = SHEET_R2) -> Optional[str]:
    """Read the as-of stamp out of a sheet banner."""
    import re
    if sheet not in wb.sheetnames:
        return None
    for row in wb[sheet].iter_rows(values_only=True):
        for c in row:
            if c:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", str(c))
                if m:
                    return m.group(1)
        break
    return None
