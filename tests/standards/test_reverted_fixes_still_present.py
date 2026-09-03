"""Sprint A · Standard S15 · Regression tests for previously-reverted fixes.

Some fixes on 2026-09-02 were reverted twice through stash/rebase chaos:
- wave_regression.A23 admin-filter (reverted 2x, restored 3x)
- xlsx_validator.I20 admin-filter (reverted 1x, restored 2x)

These tests fail the build if the fixes are absent, preventing silent
regression via file drift.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_a23_admin_filter_present_in_wave_regression():
    """A23 (Historical-lineage validation for Exit History) must import
    _is_administrative_exit and exclude admin events from _closed_reg."""
    fp = _ROOT / "backend/research/wave_regression.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "_a23_is_admin" in src, (
        "A23 admin-filter has been reverted. "
        "Restore the import of _is_administrative_exit from "
        "scripts.build_aegis_3sheet_workbook and the structural admin "
        "exclusion in the A23 _closed_reg loop."
    )
    assert "if _a23_is_admin(_o, _ep_a, _xp_a):" in src, (
        "A23 admin-check line missing. Same fix must be re-applied."
    )


def test_i20_admin_filter_present_in_xlsx_validator():
    """I20 (Registry-CLOSED in Exit History) must exclude admin events
    from closed_tks_prod using the same structural filter."""
    fp = _ROOT / "backend/delivery/xlsx_validator.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "_i20_is_admin" in src, (
        "I20 admin-filter has been reverted. "
        "Restore the import of _is_administrative_exit and the "
        "structural admin exclusion in check_closed_tickers_in_exit_history."
    )
    assert "if _i20_is_admin(o, _ep, _xp):" in src, (
        "I20 admin-check line missing."
    )


def test_orphan_audit_emits_admin_events():
    """_emit_orphan_audit_for_retired must emit both RETIRED_RUNNER_CLOSED
    and ADMIN_ZERO_DELTA_CLOSED entries. Without the admin sink, A23
    flags production-runner admin events as silently lost and blocks USA delivery."""
    fp = _ROOT / "scripts/build_aegis_3sheet_workbook.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "closed_admin_90d" in src, (
        "closed_admin_90d classification missing from _load_registry. "
        "Without this, admin events aren't routed to orphan_audit sink."
    )
    assert "ADMIN_ZERO_DELTA_CLOSED" in src, (
        "orphan_audit emitter missing ADMIN_ZERO_DELTA_CLOSED kind. "
        "Restore the admin events emission block in _emit_orphan_audit_for_retired."
    )


def test_is_administrative_exit_uses_structural_signals_only():
    """S7 · _is_administrative_exit must use ONLY structural signals
    (same-day OR entry==exit) · no hardcoded string matches on closed_reason."""
    fp = _ROOT / "scripts/build_aegis_3sheet_workbook.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    # Find the _is_administrative_exit function body
    start = src.find("def _is_administrative_exit")
    assert start > 0, "_is_administrative_exit function missing"
    end = src.find("\ndef ", start + 1)
    body = src[start:end if end > 0 else len(src)]
    # Must NOT contain string-match patterns on closed_reason
    forbidden = ["reason.startswith(", "reason.lower()", "reason ==", 'reason.upper()']
    for pattern in forbidden:
        assert pattern not in body, (
            f"_is_administrative_exit contains forbidden string-match pattern "
            f"`{pattern}` · structural signals only (same-day OR zero-Δ price)."
        )


def test_telegram_sender_uses_dated_filename():
    """Sender must attach dated per-market file, not undated latest-alias."""
    fp = _ROOT / "scripts/telegram_command_center_send.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "_dated_path = out_path.parent / f\"aegis_{mkt_key.lower()}_{_asof_send}.xlsx\"" in src, (
        "Dated-filename attachment logic has been reverted. "
        "Sender must attach aegis_{market}_YYYY-MM-DD.xlsx not aegis_history_{market}.xlsx."
    )


def test_r1_producer_guard_present():
    """opportunity_registry.get_or_create must refuse to create R1 positions
    when retirement is active."""
    fp = _ROOT / "backend/research/opportunity_registry.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "_log_retirement_block" in src, (
        "R1 producer guard has been reverted. "
        "get_or_create must import is_retired and refuse creation for retired runners."
    )
    assert "is_retired(root, runner)" in src, (
        "Retirement check missing from get_or_create."
    )


def test_3sheet_restore_present_in_legacy_sender():
    """Legacy sender must restore 3-sheet canonical after its own 5-sheet save."""
    fp = _ROOT / "scripts/telegram_command_center_send.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "SINGLE-SOURCE-OF-TRUTH RESTORE" in src, (
        "3-sheet canonical restore block has been reverted. "
        "Restore the block that rebuilds the 3-sheet workbook after wb2.save."
    )
