"""A derived cell must agree with the cells it is derived from · A8/A9.

CEO 2026-11-07.

WHAT WENT WRONG
---------------
A8 asserts `Current Perf % == (Current/Entry - 1) x 100` for OPEN rows;
A9 asserts the same identity for realized P&L on EXIT rows. Measured on
the unified history at HEAD 836f1dbf5:

    A8  708 violating rows   704 USA ·   4 INDIA
    A9  183 violating rows   USA only

Every one of them quoted a literal 0 while the two prices differed:

    CBOE  Day=1  Trading Days=33  entry=341.61  current=345.21  perf=0
    REGN  Day=1  Trading Days=12  entry=942.85  current=930.67  perf=0
    UBER  EXIT            entry=78.03   exit=75.42   exit_pnl=0

`Day=1` sitting beside `Trading Days=33` is the tell: the 0 is a FOSSIL.
It was correct when written - entry had resolved to the current price, so
the delta genuinely was zero - and a later pass corrected Entry Price
without recomputing the cell that depends on it. The same shape as the
reconciler that kept describing the previous CURRENT after a repair: fix
one artifact, leave its dependent stale.

It was also ONGOING, not historical: 234 of 521 rows on 2026-11-03 and
85 of 517 on 2026-11-04, with 0 on 2026-11-02. So this is not a
one-time cleanup; the writer needed the fix.

WHAT IS ASSERTED
----------------
That the derived value is reconciled from its inputs as a final pass,
whichever upstream path set them - and that the three things which must
NOT happen, do not:

  · a fabricated price (only the two recorded numbers are used)
  · a missing value silently becoming 0 (missing stays unavailable)
  · a legitimate zero being destroyed (entry == current really is 0)

A8/A9 themselves are untouched. Neither is weakened, and neither is in
BLOCKING_CODES, so this was never a delivery blocker - it was a
correctness defect in a number the operator reads.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.delivery.telegram.detail_xlsx import COLUMNS, _reconcile_active_pnl

_ROOT = Path(__file__).resolve().parents[2]
_NAMES = [n for (n, _w) in COLUMNS]
I_STATUS = _NAMES.index("Status")
I_ENTRY = _NAMES.index("Entry Price")
I_CUR = _NAMES.index("Current Price")
I_PERF = _NAMES.index("Current Perf %")
I_XPNL = _NAMES.index("Exit P&L %")


def _row(status, entry, current, perf="", xpnl=""):
    r = [""] * len(_NAMES)
    r[I_STATUS] = status
    r[I_ENTRY] = entry
    r[I_CUR] = current
    r[I_PERF] = perf
    r[I_XPNL] = xpnl
    return r


# ─────────────────────────────────────────────────────────────
# 1 · entry != current must never render as literal zero
# ─────────────────────────────────────────────────────────────

class TestTheFossilZeroIsRepaired:

    def test_an_open_row_gets_the_real_delta(self):
        r = _row("STRONG BUY", 341.61, 345.21, perf=0)     # CBOE, measured
        assert _reconcile_active_pnl([r]) == 1
        assert r[I_PERF] == pytest.approx(1.05, abs=0.01)

    def test_a_negative_delta_is_rendered_negative(self):
        r = _row("HOLD", 942.85, 930.67, perf=0)           # REGN, measured
        _reconcile_active_pnl([r])
        assert r[I_PERF] == pytest.approx(-1.29, abs=0.01)

    def test_an_exit_row_gets_the_real_realized_pnl(self):
        r = _row("EXIT", 78.03, 75.42, perf="", xpnl=0)    # UBER, measured
        assert _reconcile_active_pnl([r]) == 1
        assert r[I_XPNL] == pytest.approx(-3.34, abs=0.01)

    def test_a_correct_value_is_left_alone(self):
        r = _row("BUY", 200.0, 190.0, perf=-5.0)
        assert _reconcile_active_pnl([r]) == 0
        assert r[I_PERF] == -5.0

    def test_no_price_is_ever_invented(self):
        """Only the two recorded numbers are used."""
        r = _row("BUY", 100.0, 110.0, perf=0)
        _reconcile_active_pnl([r])
        assert r[I_ENTRY] == 100.0, "entry price must not be rewritten"
        assert r[I_CUR] == 110.0, "current price must not be rewritten"
        assert r[I_PERF] == pytest.approx(10.0, abs=0.01)


# ─────────────────────────────────────────────────────────────
# 2 · missing is not zero
# ─────────────────────────────────────────────────────────────

class TestMissingIsDistinctFromZero:

    @pytest.mark.parametrize("entry,current", [
        (None, 45.0), (45.0, None), (None, None),
        ("UNAVAILABLE", 45.0), (45.0, "UNAVAILABLE"),
        (0, 45.0),                      # entry 0 cannot yield a return
        (-5.0, 45.0),                   # negative entry is not a price
    ])
    def test_an_unavailable_price_blanks_rather_than_zeroes(self, entry,
                                                             current):
        r = _row("BUY", entry, current, perf=0)
        _reconcile_active_pnl([r])
        assert r[I_PERF] == "", (
            "0 asserts 'no change' · with no usable price that is a "
            "specific and wrong claim")
        assert r[I_PERF] != 0

    def test_a_blank_stays_blank(self):
        r = _row("BUY", None, None, perf="")
        assert _reconcile_active_pnl([r]) == 0
        assert r[I_PERF] == ""

    def test_a_boolean_is_not_treated_as_a_price(self):
        """True == 1 in Python · a bool must not become a 1.00 price."""
        r = _row("BUY", True, 45.0, perf=0)
        _reconcile_active_pnl([r])
        assert r[I_PERF] == ""


# ─────────────────────────────────────────────────────────────
# 3 · a legitimate zero survives
# ─────────────────────────────────────────────────────────────

class TestLegitimateZeroIsPreserved:

    def test_entry_equal_to_current_really_is_zero(self):
        r = _row("HOLD", 100.0, 100.0, perf=0)
        assert _reconcile_active_pnl([r]) == 0
        assert r[I_PERF] == 0, (
            "a day-0 admission genuinely has no delta · destroying that "
            "would be as wrong as the fossil")

    def test_a_zero_is_written_when_the_delta_really_is_zero(self):
        r = _row("HOLD", 100.0, 100.0, perf=7.5)      # wrong, non-zero
        assert _reconcile_active_pnl([r]) == 1
        assert r[I_PERF] == 0

    def test_an_exit_with_no_realized_move_keeps_zero(self):
        r = _row("EXIT", 50.0, 50.0, perf="", xpnl=0)
        assert _reconcile_active_pnl([r]) == 0
        assert r[I_XPNL] == 0


# ─────────────────────────────────────────────────────────────
# 4 · exit rows must not carry an active-side value
# ─────────────────────────────────────────────────────────────

class TestExitRowsKeepTheirSidesStraight:

    def test_an_active_value_on_an_exit_row_is_blanked(self):
        r = _row("EXIT", 100.0, 90.0, perf=-10.0, xpnl=-10.0)
        _reconcile_active_pnl([r])
        assert r[I_PERF] == "", "I3/A9 · EXIT rows carry no active P&L"
        assert r[I_XPNL] == pytest.approx(-10.0, abs=0.01)

    def test_an_open_row_keeps_its_exit_cell_untouched(self):
        r = _row("BUY", 100.0, 110.0, perf=0, xpnl="")
        _reconcile_active_pnl([r])
        assert r[I_XPNL] == "", "an open row has no realized P&L"


# ─────────────────────────────────────────────────────────────
# 5 · it is wired, and it runs LAST
# ─────────────────────────────────────────────────────────────

class TestItIsWiredAfterEveryCorrectingPass:

    @staticmethod
    def _unified_src() -> str:
        src = (_ROOT / "backend" / "delivery" / "telegram"
               / "detail_xlsx.py").read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if (isinstance(n, ast.FunctionDef)
                    and n.name == "build_unified_history"):
                return "\n".join(src.splitlines()[n.lineno - 1: n.end_lineno])
        raise AssertionError("build_unified_history not found")

    def test_reconciliation_is_called_when_the_history_is_built(self):
        assert "_reconcile_active_pnl(" in self._unified_src()

    def test_it_runs_after_the_lifecycle_validator(self):
        """Any pass that may correct an Entry Price must come first, or
        the derived cell is stale again the moment it is written."""
        body = self._unified_src()
        i_val = body.find("_validate_no_lifecycle_violations(")
        i_rec = body.find("_reconcile_active_pnl(")
        assert -1 < i_val < i_rec

    def test_the_audit_itself_was_not_weakened(self):
        """A8/A9 keep their own tolerance and their own assertions."""
        src = (_ROOT / "backend" / "research"
               / "lifecycle_stabilization.py").read_text(encoding="utf-8")
        assert "tol_pct = 1.0" in src
        assert '"A8", "Active P&L formula"' in src
        assert '"A9", "Exit P&L formula"' in src
        assert "_reconcile_active_pnl" not in src, (
            "the audit must not import the thing it audits")


# ─────────────────────────────────────────────────────────────
# 6 · both markets, against the real history
# ─────────────────────────────────────────────────────────────

class TestBothMarketsAgreeWithTheirOwnPrices:

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a8_and_a9_pass_on_the_shipped_history(self, market):
        """Measured, not asserted in the abstract.

        Skips rather than fails if the unified history is absent, since
        a fresh checkout legitimately has none.
        """
        from backend.research.lifecycle_stabilization import (
            audit_a8_a9_pnl_formulas)
        if not (_ROOT / "reports" / "telegram" / "aegis_history.xlsx").exists():
            pytest.skip("unified history not present in this checkout")
        a8, a9 = audit_a8_a9_pnl_formulas(_ROOT, market)
        assert a8.status == "PASS", "%s A8: %s · %s" % (
            market, a8.detail, (a8.violations or [])[:3])
        assert a9.status == "PASS", "%s A9: %s · %s" % (
            market, a9.detail, (a9.violations or [])[:3])
