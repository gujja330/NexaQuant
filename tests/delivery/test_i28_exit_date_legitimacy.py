"""I28 must not demand a traded close for a row that asserts no price.

CEO 2026-10-31 · USA delivery was blocked for weeks while every gate in
the run contract reported CERTIFIED. The blocker was I28, on two rows:

    WBD   record ORPHAN AUTO-CLOSE  exit_price null          exit 2026-08-26
    PSKY  record ORPHAN AUTO-CLOSE  exit_price 9.34 == entry exit 2026-08-26

I28 exists because "a displayed exit that does not reconcile is not
shippable". That premise needs a DISPLAYED price. An orphan auto-close
whose exit price is blank, or identical to its entry, claims no market
exit - its exit date is the day the orphan was DETECTED. Requiring a
traded close for it is a category error.

The existing freshness-gap exemption could not catch these: it skips when
the exit date is AFTER the parquet's last bar, and both tickers have
near-empty parquets whose single bar comes LATER than the exit date.

The exemption is deliberately narrow. 485 of USA's 490 orphan rows do
display a distinct exit price and must still face the full check, so
these tests pin both directions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("openpyxl")

from backend.delivery import xlsx_validator as xv

HDR = ["Exit Date", "Ticker", "Sector", "Market", "Engine", "Record Type",
       "Entry Date", "Entry Price", "Exit Price", "P&L %", "Holding Days",
       "Exit Reason"]
EXIT_DATE = "2026-08-26"
ENTRY_DATE = "2026-08-11"
ASOF = "2026-10-30"


def _book(tmp: Path, rows: list) -> Path:
    """A two-sheet workbook shaped like the shipped one · banner, header r4."""
    from openpyxl import Workbook
    wb = Workbook()
    cur = wb.active
    cur.title = "CURRENT"
    cur.cell(1, 1).value = f"AEGIS USA · CURRENT · workbook {ASOF}"
    ws = wb.create_sheet("EXIT HISTORY")
    ws.cell(1, 1).value = f"AEGIS USA · EXIT HISTORY · as of {ASOF}"
    for j, h in enumerate(HDR, start=1):
        ws.cell(4, j).value = h
    for i, r in enumerate(rows, start=5):
        for j, v in enumerate(r, start=1):
            ws.cell(i, j).value = v
    p = tmp / "reports" / "telegram" / "aegis_history_usa.xlsx"
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    return p


def _row(ticker, record_type, entry_price, exit_price):
    return [EXIT_DATE, ticker, "Tech", "USA", "R2", record_type, ENTRY_DATE,
            entry_price, exit_price, None, 15, "Auto-close · orphaned position"]


def _parquet(tmp: Path, ticker: str, dates: list):
    """A near-empty price file · exactly the WBD/PSKY shape."""
    d = tmp / "usa" / "data" / "raw" / "us"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": [10.0] * len(dates)},
                      index=pd.to_datetime(dates))
    df.to_parquet(d / f"{ticker}_D1.parquet")


def _i28(tmp: Path, rows: list):
    v = xv.XlsxValidator(tmp, "usa", _book(tmp, rows))
    return v.check_exit_date_legitimate()


def _codes(res):
    return {v["ticker"] for v in res.violations}


# ── the two rows that blocked delivery ──────────────────────────────────
def test_blank_exit_price_is_not_a_violation(tmp_path):
    """WBD · exit_price null · nothing displayed, nothing to falsify."""
    _parquet(tmp_path, "WBD", ["2026-10-05"])
    res = _i28(tmp_path, [_row("WBD", "ORPHAN AUTO-CLOSE", None, None)])
    assert "WBD" not in _codes(res), (
        "a blank exit price was still required to reconcile against a "
        "traded close · this is the row that blocked USA delivery")


def test_exit_equal_to_entry_is_not_a_violation(tmp_path):
    """PSKY · exit == entry · a degenerate mark, not a sourced close."""
    _parquet(tmp_path, "PSKY", ["2026-07-29", "2026-10-16"])
    res = _i28(tmp_path, [_row("PSKY", "ORPHAN AUTO-CLOSE", 9.34, 9.34)])
    assert "PSKY" not in _codes(res)


def test_both_together_leave_the_invariant_passing(tmp_path):
    _parquet(tmp_path, "WBD", ["2026-10-05"])
    _parquet(tmp_path, "PSKY", ["2026-10-16"])
    res = _i28(tmp_path, [_row("WBD", "ORPHAN AUTO-CLOSE", None, None),
                          _row("PSKY", "ORPHAN AUTO-CLOSE", 9.34, 9.34)])
    assert res.status == "PASS", res.detail


# ── the exemption must stay narrow ──────────────────────────────────────
def test_orphan_with_a_distinct_exit_price_still_fails(tmp_path):
    """485 of 490 USA orphan rows look like this · they must stay checked.

    Without this the fix would silently disable I28 for every orphan row
    instead of correcting one category error.
    """
    _parquet(tmp_path, "ZTS", ["2026-10-05"])
    res = _i28(tmp_path, [_row("ZTS", "ORPHAN AUTO-CLOSE", 75.35, 77.52)])
    assert "ZTS" in _codes(res), (
        "an orphan row asserting a distinct exit price escaped the check · "
        "the exemption has become a bypass")


def test_realized_exit_with_no_close_still_fails(tmp_path):
    """A real trade must always reconcile, price asserted or not."""
    _parquet(tmp_path, "REAL", ["2026-10-05"])
    res = _i28(tmp_path, [_row("REAL", "REALIZED EXIT", None, None)])
    assert "REAL" in _codes(res)


@pytest.mark.parametrize("rt", ["STOP-BREACH MARK", "REALIZED EXIT"])
def test_non_administrative_record_types_are_never_exempt(tmp_path, rt):
    _parquet(tmp_path, "XYZ", ["2026-10-05"])
    res = _i28(tmp_path, [_row("XYZ", rt, 50.0, 50.0)])
    assert "XYZ" in _codes(res), (
        "%s was exempted · only orphan/administrative rows may be" % rt)


def test_exemption_does_not_fire_when_a_close_exists(tmp_path):
    """Sanity · a row with a real close on its exit date passes anyway."""
    _parquet(tmp_path, "GOOD", [EXIT_DATE])
    res = _i28(tmp_path, [_row("GOOD", "REALIZED EXIT", 10.0, 11.0)])
    assert res.status == "PASS"
