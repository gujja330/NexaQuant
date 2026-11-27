"""India two-sheet workbook round-trip checks."""
from copy import copy

from openpyxl import Workbook, load_workbook

from backend.delivery.sheets.workbook_two import _style_pnl_text, emit_current, emit_exit_history


def test_shared_pnl_font_only_changes_nonzero_numbers():
    sheet = Workbook().active
    cases = [(5.25, "FF166534"), (-5.25, "FF991B1B"), (0, None), (None, None)]
    for row, (value, expected_color) in enumerate(cases, start=1):
        cell = sheet.cell(row, 1, value)
        original_font = copy(cell.font)
        _style_pnl_text(cell)
        assert cell.value == value
        if expected_color is None:
            assert cell.font == original_font
        else:
            assert cell.font.color.rgb == expected_color


def test_india_workbook_preserves_targets_and_colors(tmp_path):
    sample_rows = [
        {"ticker": "GAIN", "target": 100.0, "current_price": 110.0, "pnl_pct": 10.0,
         "max_loss_if_stop_pct": 3.0, "action": "ACTIVE+"},
        {"ticker": "LOSS", "target": 100.0, "current_price": 90.0, "pnl_pct": -10.0,
         "max_loss_if_stop_pct": -12.0, "action": "NEW", "price_freshness": "STALE DATA"},
        {"ticker": "FLAT", "target": 100.0, "current_price": 100.0, "pnl_pct": 0.0},
        {"ticker": "MISSING", "current_price": 100.0, "pnl_pct": None},
    ]
    current = [dict(row, market="INDIA", engine="R2", entry_price=100.0,
                    position_id=row["ticker"]) for row in sample_rows]
    exits = [
        {"ticker": "LOSS", "realized_pnl_pct": -10.0, "record_type": "REALIZED EXIT"},
        {"ticker": "GAIN", "realized_pnl_pct": 10.0, "record_type": "STOP-BREACH MARK"},
        {"ticker": "FLAT", "realized_pnl_pct": 0.0, "record_type": "ADMINISTRATIVE"},
        {"ticker": "ADVISORY", "realized_pnl_pct": None, "record_type": "ADVISORY/HISTORICAL"},
    ]
    # The canonical lifecycle owns these derived values (CEO 2026-11-27); a
    # stand-in for its output must carry them exactly as it would.
    from backend.delivery.lifecycle.canonical_daily_lifecycle import decision_metrics
    for _r in current:
        _r.update(decision_metrics(_r))
    dataset = {"market": "india", "asof": "2026-11-24", "current": current, "exits": exits}
    book = Workbook()
    book.remove(book.active)
    emit_current(book, dataset)
    emit_exit_history(book, dataset)
    path = tmp_path / "aegis.xlsx"
    book.save(path)
    book = load_workbook(path)
    assert book.sheetnames == ["CURRENT", "EXIT HISTORY"]

    current_sheet, history = book.worksheets
    cols = {cell.value: cell.column for cell in current_sheet[7]}
    assert [current_sheet.cell(i, cols["Target Status"]).value for i in range(8, 12)] == [
        "TARGET EXCEEDED", "TARGET NOT REACHED", "TARGET REACHED", "TARGET NOT AVAILABLE",
    ]
    assert [current_sheet.cell(i, cols["Target"]).value for i in range(8, 11)] == [100.0] * 3
    assert current_sheet.cell(8, cols["Profit Giveback (pp)"]).value == 7.0
    assert current_sheet.cell(9, cols["Action"]).fill.fgColor.rgb.endswith("DBEAFE")
    assert current_sheet.cell(9, cols["Price Freshness"]).fill.fgColor.rgb.endswith("FEF3C7")
    gain = current_sheet.cell(8, cols["P&L %"])
    loss = current_sheet.cell(9, cols["P&L %"])
    assert (gain.value, gain.number_format, gain.fill.fgColor.rgb) == (10.0, "0.00", "FFDCFCE7")
    assert (loss.value, loss.number_format, loss.fill.fgColor.rgb) == (-10.0, "0.00", "FFFEE2E2")
    assert gain.font.color.rgb == "FF166534" and loss.font.color.rgb == "FF991B1B"
    assert current_sheet.cell(10, cols["P&L %"]).fill.patternType is None
    history_pnl = next(cell.column for cell in history[4] if cell.value == "P&L %")
    assert history.cell(5, history_pnl).fill.fgColor.rgb == "FFFEE2E2"
    assert history.cell(6, history_pnl).fill.fgColor.rgb == "FFDCFCE7"
    assert history.cell(5, history_pnl).font.color.rgb == "FF991B1B"
    assert current_sheet.freeze_panes == "C8" and history.freeze_panes == "C5"
    assert current_sheet.auto_filter.ref and history.auto_filter.ref
    assert len(current_sheet.conditional_formatting) == 2
    assert len(history.conditional_formatting) == 1
    book.close()
