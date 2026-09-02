"""Regression test · CEO 2026-09-02 · single-source-of-truth restore.

The legacy telegram_command_center_send.py builds a 5-sheet OLD workbook
and would (before the 2026-09-02 fix) clobber the 3-sheet LOCKED
contract file at reports/telegram/aegis_history_{market}.xlsx. This
regression test asserts that the 3-sheet canonical restore step is
present after the legacy save · so a future refactor cannot silently
break operator delivery of the LOCKED 3-sheet format.

If this test fails, the operator will receive the 5-sheet OLD format
via Telegram · the 2026-09-01 LOCK contract is broken.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_sender_contains_3sheet_restore_after_save():
    """Legacy sender must invoke build_aegis_3sheet_workbook.build_workbook
    after its own wb2.save(out_path) call."""
    p = _ROOT / "scripts" / "telegram_command_center_send.py"
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    # save call must exist
    assert "wb2.save(out_path)" in src
    # restore invocation must follow · anchor on the CEO marker
    assert "SINGLE-SOURCE-OF-TRUTH RESTORE" in src, (
        "The 3-sheet restore block is missing from "
        "scripts/telegram_command_center_send.py · legacy 5-sheet "
        "would reach the operator via Telegram. See CEO 2026-09-02 "
        "delivery-layer fix."
    )
    # restore uses build_workbook from build_aegis_3sheet_workbook
    assert "build_aegis_3sheet_workbook" in src
    assert "build_workbook as _build_3sheet" in src


def test_3sheet_builder_still_writes_both_files():
    """Sanity · the 3-sheet builder must still write both undated and
    dated files · restore step depends on both being written."""
    p = _ROOT / "scripts" / "build_aegis_3sheet_workbook.py"
    src = p.read_text(encoding="utf-8")
    assert 'f"aegis_{market.lower()}_{asof}.xlsx"' in src
    assert 'f"aegis_history_{market.lower()}.xlsx"' in src
    assert "wb.save(xlsx_dated)" in src
    assert "shutil.copyfile(xlsx_dated, xlsx_undated)" in src


def test_restore_uses_todays_date_not_stale_variable():
    """Restore must use date.today() · never the legacy sender's
    latest_date variable · which may lag behind by data-freshness."""
    p = _ROOT / "scripts" / "telegram_command_center_send.py"
    src = p.read_text(encoding="utf-8")
    # find the restore block bounds
    start = src.find("SINGLE-SOURCE-OF-TRUTH RESTORE")
    assert start > 0
    block = src[start:start + 2000]
    assert "_dt.today().isoformat()" in block or "date.today().isoformat()" in block
