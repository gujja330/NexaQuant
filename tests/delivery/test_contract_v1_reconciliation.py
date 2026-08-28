"""AEGIS · Delivery Data Contract v1 · reconciliation regression tests.

CEO 2026-08-28 · end-to-end stabilization directive · one coherent
change. These tests encode the invariants that must NEVER be silently
regressed by future work.

Scope of this file:
  · Rule C4 · MISSING must never be silently substituted with LOW /
    PENDING / 0 for holding-no-signal rows.
  · Rule C5 · MONTHLY_SUMMARY must live on its own sheet · never as
    trailer rows inside the Exit History body.
  · Portfolio banner "Active (current)" must reconcile to the visible
    body count (banner ≠ independent worksheet scan).
  · Definitions sheet must exist in every shipped workbook.
  · P&L column format · holding-no-signal rows use the same "%" number
    format as signal rows so the operator sees consistent units.

The tests operate against the SHIPPED XLSX at
`reports/telegram/aegis_history_india.xlsx` if it exists · they are
resilient to CI environments that have not built the XLSX (they SKIP
rather than FAIL). This mirrors how xlsx_validator + I20/A23 already
guard against absent artifacts.
"""
from __future__ import annotations

import pytest
from pathlib import Path

_XLSX_INDIA = Path("reports/telegram/aegis_history_india.xlsx")
_XLSX_USA = Path("reports/telegram/aegis_history_usa.xlsx")


def _load_wb(p: Path):
    if not p.exists():
        pytest.skip(f"artifact not present · {p}")
    from openpyxl import load_workbook
    return load_workbook(p, read_only=True, data_only=True)


def _portfolio_rows(wb):
    ws = wb["Portfolio"]
    return [tuple(r) for r in ws.iter_rows(values_only=True)
             if any(c not in (None, "") for c in r)]


def _exit_rows(wb):
    if "Exit History (90d)" not in wb.sheetnames:
        return []
    ws = wb["Exit History (90d)"]
    return [tuple(r) for r in ws.iter_rows(values_only=True)
             if any(c not in (None, "") for c in r)]


# ── C4 · MISSING ≠ LOW · MISSING ≠ PENDING ────────────────────────


def test_c4_no_low_urgency_fabrication_in_holding_rows():
    """Path-A holding rows (Registry-ACTIVE · no signal today) MUST NOT
    contain 'LOW' as Urgency. Engine did not evaluate · row must show
    'MISSING' semantics ('—' em-dash)."""
    wb = _load_wb(_XLSX_INDIA)
    rows = _portfolio_rows(wb)
    # Find header row
    hdr_idx = None
    for i, r in enumerate(rows):
        if r[0] and "Ticker" in str(r[0]):
            hdr_idx = i
            break
    assert hdr_idx is not None, "Portfolio header row not found"
    hdr = rows[hdr_idx]
    # Find Urgency column
    urgency_col = None
    for c, name in enumerate(hdr):
        if name and "Urgency" in str(name):
            urgency_col = c
            break
    assert urgency_col is not None, "Urgency column not found in Portfolio header"
    body = rows[hdr_idx + 1:]
    # Any row whose ACTION mentions "holding · no signal" is a Path-A row
    violations = []
    for r in body:
        action = str(r[1]) if len(r) > 1 and r[1] else ""
        if "holding" in action.lower() and "no signal" in action.lower():
            urg = str(r[urgency_col]) if urgency_col < len(r) and r[urgency_col] else ""
            if "LOW" in urg.upper():
                violations.append((r[0], urg))
    assert not violations, (
        f"Rule C4 violation · {len(violations)} holding-no-signal rows "
        f"have fabricated LOW Urgency · engine did not evaluate these · "
        f"first 3: {violations[:3]}"
    )
    wb.close()


def test_c4_no_pending_quality_fabrication_in_holding_rows():
    """Path-A holding rows MUST NOT contain 'PENDING' as Inv Quality.
    Engine did not evaluate · row must show 'MISSING' semantics."""
    wb = _load_wb(_XLSX_INDIA)
    rows = _portfolio_rows(wb)
    hdr_idx = None
    for i, r in enumerate(rows):
        if r[0] and "Ticker" in str(r[0]):
            hdr_idx = i
            break
    assert hdr_idx is not None
    hdr = rows[hdr_idx]
    quality_col = None
    for c, name in enumerate(hdr):
        if name and "Inv Quality" in str(name):
            quality_col = c
            break
    assert quality_col is not None, "Inv Quality column not found"
    body = rows[hdr_idx + 1:]
    violations = []
    for r in body:
        action = str(r[1]) if len(r) > 1 and r[1] else ""
        if "holding" in action.lower() and "no signal" in action.lower():
            q = str(r[quality_col]) if quality_col < len(r) and r[quality_col] else ""
            if "PENDING" in q.upper():
                violations.append((r[0], q))
    assert not violations, (
        f"Rule C4 violation · {len(violations)} holding-no-signal rows "
        f"have fabricated PENDING Inv Quality · first 3: {violations[:3]}"
    )
    wb.close()


def test_c4_pnl_column_uses_percent_format_for_holding_rows():
    """Holding-no-signal rows must apply Excel '%' number format so the
    operator sees '-2.69%' not '-0.0269' · matches signal-row format."""
    if not _XLSX_INDIA.exists():
        pytest.skip("artifact not present")
    from openpyxl import load_workbook
    # Full-workbook load (not read-only) to inspect cell.number_format
    wb = load_workbook(_XLSX_INDIA, data_only=True)
    ws = wb["Portfolio"]
    hdr_row = None
    pnl_col = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 1).value and "Ticker" in str(ws.cell(r, 1).value):
            hdr_row = r
            for c in range(1, ws.max_column + 1):
                v = ws.cell(hdr_row, c).value
                if v and "P&L" in str(v):
                    pnl_col = c
                    break
            break
    assert hdr_row is not None
    assert pnl_col is not None, "P&L column not found in Portfolio header"
    violations = []
    for r in range(hdr_row + 1, ws.max_row + 1):
        action = ws.cell(r, 2).value or ""
        if "holding" in str(action).lower() and "no signal" in str(action).lower():
            cell = ws.cell(r, pnl_col)
            if cell.value is not None and isinstance(cell.value, (int, float)):
                fmt = cell.number_format or ""
                if "%" not in fmt:
                    violations.append((ws.cell(r, 1).value, cell.value, fmt))
    assert not violations, (
        f"Rule C4 violation · {len(violations)} holding-no-signal rows "
        f"have P&L stored without % number format · Excel will render "
        f"the raw decimal (looks like '-0.03' not '-2.69%') · "
        f"first 3: {violations[:3]}"
    )
    wb.close()


# ── C5 · MONTHLY_SUMMARY separate sheet ───────────────────────────


def test_c5_monthly_summary_is_a_separate_sheet():
    """Monthly Summary MUST be a first-class sheet · never trailer rows
    inside Exit History body. Validators must never need trailer-skip
    logic to survive."""
    wb = _load_wb(_XLSX_INDIA)
    sheets = wb.sheetnames
    assert "Monthly Summary" in sheets, (
        f"Monthly Summary sheet missing · rule C5 violation · "
        f"workbook has {sheets}"
    )
    wb.close()


def test_c5_exit_history_body_ends_at_lineage_row():
    """Last non-empty row of Exit History body MUST be a lineage
    (trade) row · not a decoration/summary/trailer row."""
    wb = _load_wb(_XLSX_INDIA)
    rows = _exit_rows(wb)
    if not rows:
        pytest.skip("Exit History sheet empty")
    # Last row's first cell should be a ticker (all-caps, no ── / MONTH /
    # SUMMARY / spaces).
    last = rows[-1]
    first = str(last[0]) if last[0] else ""
    forbidden = ["──", "MONTHLY", "MONTH", "SUMMARY", "TOTAL"]
    for f in forbidden:
        assert f not in first.upper(), (
            f"Rule C5 violation · Exit History body last row is a "
            f"decoration row · '{first[:50]}' · Monthly summary must be "
            f"a separate sheet"
        )


def test_c5_no_trailer_strings_in_exit_history_body():
    """No row in Exit History body should contain 'MONTHLY P&L SUMMARY'
    · that content belongs on the Monthly Summary sheet."""
    wb = _load_wb(_XLSX_INDIA)
    rows = _exit_rows(wb)
    if not rows:
        pytest.skip("Exit History sheet empty")
    for i, r in enumerate(rows, 1):
        for c_v in r:
            if c_v is None: continue
            s = str(c_v).upper()
            assert "MONTHLY P&L SUMMARY" not in s, (
                f"Rule C5 violation · Exit History body r{i} contains "
                f"trailer text '{s[:80]}' · must move to Monthly Summary sheet"
            )
    wb.close()


# ── C6 · Banner reads canonical count not worksheet scan ─────────


def test_banner_active_current_reconciles_to_visible_body():
    """Portfolio banner 'Active (current): N' must equal the number of
    visible ACTIVE / ACTIVE+ / NEW body rows. Banner must not
    independently invent a count."""
    wb = _load_wb(_XLSX_INDIA)
    rows = _portfolio_rows(wb)
    # Row 2 is the banner
    banner = str(rows[1][0]) if len(rows) > 1 and rows[1][0] else ""
    import re as _re
    m = _re.search(r"Active \(current\):\s*(\d+)", banner)
    if not m:
        pytest.skip(f"banner not in 'Active (current): N' shape · {banner[:80]}")
    stated = int(m.group(1))
    # Count body rows (exclude SUGGESTED/SHADOW · they have own header text)
    hdr_idx = None
    for i, r in enumerate(rows):
        if r[0] and "Ticker" in str(r[0]):
            hdr_idx = i
            break
    body = rows[hdr_idx + 1:]
    n_visible = 0
    for r in body:
        dec = str(r[2]) if len(r) > 2 and r[2] else ""
        if any(k in dec.upper() for k in ("ACTIVE", "NEW")) and "SUGGESTED" not in dec.upper():
            n_visible += 1
    # Banner must equal visible count (banner reads what body shows)
    assert stated == n_visible, (
        f"Banner reconciliation failure · stated={stated} visible={n_visible} "
        f"· C6 violation · banner must consume same population as body"
    )
    wb.close()


# ── Definitions sheet MUST exist ──────────────────────────────────


def test_definitions_sheet_exists_in_workbook():
    """Every shipped workbook must include the Definitions sheet · so
    the operator can read scope + formula + missing-data semantics
    without leaving the file."""
    wb = _load_wb(_XLSX_INDIA)
    assert "Definitions" in wb.sheetnames, (
        f"Definitions sheet missing from India workbook · sheets={wb.sheetnames}"
    )
    wb.close()
