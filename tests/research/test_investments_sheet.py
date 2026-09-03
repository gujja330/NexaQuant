"""Tests for 01_Investments primary operator sheet (CEO 2026-09-03)."""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_investments_sheet_meta():
    from backend.delivery.sheets.investments_sheet import (
        sheet_meta, INVESTMENTS_COLUMNS, INVESTMENTS_BANNER,
    )
    m = sheet_meta()
    assert m["sheet_name"] == "01_Investments"
    # Mandatory columns per CEO 2026-09-03
    for req in ("Score", "Action", "Ticker", "Runner", "Entry Date",
                "Entry Price", "Current Price", "Unrealized P&L %",
                "Holding Days", "Dynamic Stop", "Target"):
        assert req in INVESTMENTS_COLUMNS, f"missing mandatory column: {req}"
    # Banner mentions mandatory Dynamic Stop
    assert "Dynamic Stop mandatory" in INVESTMENTS_BANNER


def test_stop_trichotomy_r2_valid_atr():
    from backend.delivery.sheets.investments_sheet import _stop_cell
    cell, prov = _stop_cell("R2", entry_price=100.0, atr=2.5)
    # Should produce numeric stop, no SUGGESTED tag
    assert "SUGGESTED" not in cell
    assert "N/A" not in cell
    assert "DATA_ERROR" not in cell
    assert float(cell) < 100.0   # Stop below entry (k=2 → 100 − 5 = 95)


def test_stop_trichotomy_r1_gets_suggested_tag():
    from backend.delivery.sheets.investments_sheet import _stop_cell
    cell, prov = _stop_cell("R1", entry_price=100.0, atr=2.5)
    assert "SUGGESTED" in cell
    assert prov == "atr14_suggested_r1_no_auto_exit"


def test_stop_trichotomy_r1_no_atr_returns_advisory_only():
    from backend.delivery.sheets.investments_sheet import _stop_cell
    cell, prov = _stop_cell("R1", entry_price=100.0, atr=None)
    assert "N/A" in cell
    assert "advisory" in cell.lower()


def test_stop_trichotomy_r2_data_error_when_missing_atr():
    from backend.delivery.sheets.investments_sheet import _stop_cell
    cell, prov = _stop_cell("R2", entry_price=100.0, atr=None)
    assert cell.startswith("DATA_ERROR")


def test_stop_trichotomy_r2_data_error_when_missing_entry():
    from backend.delivery.sheets.investments_sheet import _stop_cell
    cell, prov = _stop_cell("R2", entry_price=None, atr=2.5)
    assert cell.startswith("DATA_ERROR")


def test_score_bounded_0_100():
    from backend.delivery.sheets.investments_sheet import (
        _score_for_r2_new, _score_for_r1_new, _score_for_active,
    )
    for score in [
        _score_for_r2_new(1.0, 1.0), _score_for_r2_new(-1.0, 0.0),
        _score_for_r1_new("STRONG BUY", 100), _score_for_r1_new(None, None),
        _score_for_active(20, 50, 90), _score_for_active(-30, 0, 20),
    ]:
        assert 0 <= score <= 100


def test_investments_sheet_never_bare_unavailable_for_stop():
    """Every Dynamic Stop cell must be one of: numeric · SUGGESTED · N/A · DATA_ERROR."""
    import io, sys
    from openpyxl import load_workbook
    for m in ("india", "usa"):
        p = Path(__file__).resolve().parents[2] / "reports" / "telegram" / f"aegis_{m}_2026-09-03.xlsx"
        if not p.exists(): continue
        wb = load_workbook(p)
        if "01_Investments" not in wb.sheetnames: continue
        ws = wb["01_Investments"]
        # Header row 4 · Dynamic Stop is column 11
        for r in range(5, ws.max_row + 1):
            action = ws.cell(r, 2).value
            if action is None or str(action).startswith("("): continue
            # Skip header/section rows · Action cell contains literal "Action" text
            if str(action).strip() == "Action": continue
            stop_val = ws.cell(r, 11).value
            if stop_val is None: continue
            # Skip legend rows (start of Score/Action explanations)
            if str(stop_val).strip() in ("Target", ""): continue
            s = str(stop_val)
            # Must NOT be bare "UNAVAILABLE"
            assert s != "UNAVAILABLE", f"{m} row {r} · bare UNAVAILABLE stop (CEO §36 trichotomy violation)"
            # Must be one of the four allowed states
            is_valid = (
                s.replace(".", "", 1).replace("-", "", 1).isdigit()
                or "SUGGESTED" in s
                or "N/A" in s
                or "DATA_ERROR" in s
            )
            assert is_valid, f"{m} row {r} · stop value {s!r} not in trichotomy"


def test_investments_sheet_is_first_tab():
    from openpyxl import load_workbook
    for m in ("india", "usa"):
        p = Path(__file__).resolve().parents[2] / "reports" / "telegram" / f"aegis_{m}_2026-09-03.xlsx"
        if not p.exists(): continue
        wb = load_workbook(p)
        if "01_Investments" not in wb.sheetnames: continue
        assert wb.sheetnames[0] == "01_Investments", (
            f"{m} · 01_Investments must be FIRST tab · got {wb.sheetnames[0]}"
        )
