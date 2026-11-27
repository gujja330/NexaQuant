"""Currency follows the market; rows stay one line. CEO 2026-11-26.

Extending India's 37-column layout to USA carried India's table styling
with it, which formatted every USA price as "INR ...". And row heights
were stretched to fit the whole wrapped Reason - 78pt rows in India,
42pt in USA - which read as large gaps between rows.
"""
from pathlib import Path

from openpyxl import Workbook

from backend.delivery.sheets.workbook_two import _style_india_table

COLS = ["Ticker", "Entry Price", "Current Market Cap", "Reason"]


def _sheet(reason="x " * 400):
    wb = Workbook()
    ws = wb.active
    for j, c in enumerate(COLS, 1):
        ws.cell(7, j, c)
    for j, v in enumerate(["AAA", 123.45, 5_000_000_000, reason], 1):
        ws.cell(8, j, v)
    return ws


def test_usa_prices_are_dollars():
    ws = _sheet()
    _style_india_table(ws, COLS, 7, 8, currency="USD")
    assert ws.cell(8, 2).number_format == '"$"#,##0.00'
    assert ws.cell(8, 3).number_format == '"$"#,##0'


def test_india_prices_stay_rupees():
    ws = _sheet()
    _style_india_table(ws, COLS, 7, 8)
    assert ws.cell(8, 2).number_format == '"INR "#,##0.00'


def test_a_long_reason_does_not_stretch_the_row():
    ws = _sheet()
    _style_india_table(ws, COLS, 7, 8)
    assert ws.row_dimensions[8].height == 18
    assert ws.cell(8, 4).alignment.wrap_text is False
    assert len(ws.cell(8, 4).value) > 700, "the text itself must not be cut"


def test_emit_current_passes_the_market_currency():
    src = (Path(__file__).resolve().parents[2] / "backend" / "delivery"
           / "sheets" / "workbook_two.py").read_text(encoding="utf-8")
    assert 'currency="USD" if str(d.get("market", "")).lower() == "usa"' in src
