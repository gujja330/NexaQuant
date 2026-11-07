"""Days Held on CURRENT · CEO 2026-11-07, under an explicit lock override.

WHY
---
CURRENT showed `Entry Date` but no duration, so holding age had to be
worked out by hand for every open position. EXIT HISTORY already carried
`Holding Days`; this is the same measure for positions that are still
open.

Shipped under the verbatim override "override the xlsx contract lock",
which is the only approved change to the locked 23-column CURRENT
contract. CURRENT goes 23 -> 24. Nothing is reordered or renamed and
EXIT HISTORY is untouched.

THE ONE DECISION THAT MATTERS
-----------------------------
The value is derived from the LIFECYCLE as-of, never `date.today()`.

A wall-clock derivation would re-print a different number every time the
workbook was rebuilt, and rebuilding a historical workbook would show
today's age against an old entry. That is the same defect class as the
freshness checks that certified `age 0` over day-old bars, and as the
`recorded_utc` churn that made lineage records look non-idempotent.
Taking it from the artifact's own as-of keeps a rebuild deterministic.

An unavailable value renders as the contract's em-dash, not 0 - a zero
would read as "entered today", which is a specific and wrong claim.
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from backend.delivery.sheets import workbook_two as w2

_ROOT = Path(__file__).resolve().parents[2]
DASH = "—"


# ─────────────────────────────────────────────────────────────
# the derivation
# ─────────────────────────────────────────────────────────────

class TestTheDerivation:

    def test_entry_on_the_asof_is_zero(self):
        assert w2._days_held("2026-11-07", "2026-11-07") == 0

    def test_one_calendar_day_is_one(self):
        assert w2._days_held("2026-11-06", "2026-11-07") == 1

    def test_a_multi_day_holding_is_the_difference(self):
        assert w2._days_held("2026-08-06", "2026-11-07") == 93

    def test_weekends_are_included(self):
        """Calendar days, matching EXIT HISTORY's Holding Days.

        2026-11-06 is a Friday; Monday is the 9th. Three calendar days,
        not one trading day - and the column is named Days Held, not
        Trading Days, precisely so a reader is not misled.
        """
        assert date(2026, 11, 6).weekday() == 4
        assert w2._days_held("2026-11-06", "2026-11-09") == 3

    def test_a_long_holding_crossing_a_year_boundary(self):
        assert w2._days_held("2025-12-31", "2026-01-01") == 1

    def test_a_missing_entry_date_does_not_invent_a_value(self):
        for bad in (None, "", "   "):
            assert w2._days_held(bad, "2026-11-07") == DASH

    def test_an_invalid_date_follows_the_contract_dash(self):
        for bad in ("UNAVAILABLE", "n/a", "2026-13-45", "yesterday", 0):
            assert w2._days_held(bad, "2026-11-07") == DASH

    def test_a_missing_asof_does_not_fall_back_to_today(self):
        assert w2._days_held("2026-08-06", None) == DASH
        assert w2._days_held("2026-08-06", "") == DASH

    def test_an_entry_after_the_asof_is_not_rendered_as_a_duration(self):
        """A negative age is a lifecycle defect, not a holding period."""
        assert w2._days_held("2026-11-08", "2026-11-07") == DASH

    def test_zero_is_never_used_for_unknown(self):
        """0 would read as 'entered today' · a specific, wrong claim."""
        assert w2._days_held(None, "2026-11-07") != 0
        assert w2._days_held("garbage", "2026-11-07") != 0


class TestItIsDeterministicNotWallClock:

    def test_the_same_inputs_always_give_the_same_value(self):
        a = w2._days_held("2026-08-06", "2026-11-07")
        b = w2._days_held("2026-08-06", "2026-11-07")
        assert a == b == 93

    def test_a_historical_asof_reproduces_its_historical_value(self):
        """Rebuilding an old workbook must not print today's age."""
        assert w2._days_held("2026-08-06", "2026-08-20") == 14
        assert w2._days_held("2026-08-06", "2026-09-04") == 29

    def test_the_value_does_not_depend_on_todays_date(self, monkeypatch):
        """Freeze a different 'today' and the answer must not move."""
        import datetime as _dt

        class _Frozen(_dt.date):
            @classmethod
            def today(cls):
                return cls(2030, 1, 1)

        monkeypatch.setattr(_dt, "date", _Frozen)
        assert w2._days_held("2026-08-06", "2026-11-07") == 93

    def test_the_helper_never_calls_today(self):
        """Structural · scanned from the AST, not the prose."""
        src = (_ROOT / "backend" / "delivery" / "sheets"
               / "workbook_two.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_days_held")
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                assert name not in ("today", "now", "utcnow"), (
                    "a wall-clock derivation re-prints differently on every "
                    "rebuild · the as-of comes from the artifact")


# ─────────────────────────────────────────────────────────────
# the column contract
# ─────────────────────────────────────────────────────────────

class TestTheColumnContract:

    def test_current_went_from_23_to_24(self):
        assert len(w2.CURRENT_COLUMNS) == 24
        assert len(w2.CURRENT_COLUMNS_R2) == 23      # 22 + Days Held

    def test_days_held_sits_immediately_after_entry_date(self):
        i = w2.CURRENT_COLUMNS.index("Days Held")
        assert w2.CURRENT_COLUMNS[i - 1] == "Entry Date"
        assert w2.CURRENT_COLUMNS[i + 1] == "Entry Price"

    def test_exit_history_is_unchanged(self):
        assert len(w2.EXIT_COLUMNS) == 16
        assert "Holding Days" in w2.EXIT_COLUMNS
        assert "Days Held" not in w2.EXIT_COLUMNS, (
            "EXIT HISTORY already has Holding Days · adding a second "
            "name for one measure is how vocabularies fork")

    def test_nothing_else_was_reordered_or_renamed(self):
        without = [c for c in w2.CURRENT_COLUMNS_R2 if c != "Days Held"]
        assert without == [
            "Market", "Ticker", "Engine", "Action", "Admission Status",
            "Entry Date", "Entry Price", "Last Price", "Market Data As-of",
            "P&L %", "Confidence %", "Sector", "Current Market Cap",
            "Market Cap As-of", "Size",
            "Stop", "Stop State", "Stop Distance %", "Max Loss if Stop %",
            "Target", "Position ID", "Reason"]

    def test_r3_still_adds_exactly_one_column_beside_action(self):
        assert w2.CURRENT_COLUMNS_R3 == ["R3 SHADOW"]
        i = w2.CURRENT_COLUMNS.index("R3 SHADOW")
        assert w2.CURRENT_COLUMNS[i - 1] == "Action"

    def test_the_column_widths_still_match_the_header(self):
        """A width list one short silently shifts every later column."""
        src = (_ROOT / "backend" / "delivery" / "sheets"
               / "workbook_two.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "emit_current")
        widths = None
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "enumerate"
                    and node.args and isinstance(node.args[0], ast.List)):
                cand = node.args[0].elts
                if len(cand) > 15 and all(isinstance(e, ast.Constant)
                                          for e in cand):
                    widths = cand
                    break
        assert widths is not None, "column width list not found"
        assert len(widths) == len(w2.CURRENT_COLUMNS), (
            "%d widths for %d columns" % (len(widths),
                                          len(w2.CURRENT_COLUMNS)))


class TestItUsesTheExistingAliasVocabulary:

    def test_days_held_resolves_through_the_holding_days_alias_group(self):
        """The validator already knew this vocabulary.

        xlsx_validator carries
        "Holding Days": ["Holding Days", "Days Held", "Days"], so
        inventing a fourth name would have recreated the alias drift
        that fired A19/A23 on a renamed sheet.
        """
        src = (_ROOT / "backend" / "delivery"
               / "xlsx_validator.py").read_text(encoding="utf-8")
        # There are TWO alias sets: PORTFOLIO/CURRENT and EXIT_HISTORY.
        # EXIT_HISTORY already carried "Days Held"; the Portfolio one did
        # not, and CURRENT is the sheet that now has the column - a field
        # the resolver cannot name is the alias drift that fired
        # I11/I16/I23/I27. Both must resolve it.
        groups = [src[i: i + 140]
                  for i in range(len(src))
                  if src.startswith('"Holding Days":', i)]
        assert len(groups) == 2, "expected both alias sets · got %d" % len(groups)
        for g in groups:
            assert "Days Held" in g, (
                "every alias set that names Holding Days must resolve "
                "Days Held · %s" % g[:90])

    def test_the_alias_group_itself_was_not_modified(self):
        src = (_ROOT / "backend" / "delivery"
               / "xlsx_validator.py").read_text(encoding="utf-8")
        assert src.count('"Holding Days":  ["Holding Days", "Days Held", '
                         '"Days"]') == 2, (
            "one name added to the Portfolio set · nothing renamed, "
            "nothing removed, and EXIT_HISTORY untouched")


class TestNoProductionDecisionLogicChanged:

    def test_the_change_is_confined_to_rendering(self):
        src = (_ROOT / "backend" / "delivery" / "sheets"
               / "workbook_two.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_days_held")
        body = ast.dump(fn)
        for forbidden in ("stop", "size", "threshold", "weight", "score",
                          "rank", "universe"):
            assert forbidden not in body.lower(), (
                "a display column must not touch decision logic (%s)"
                % forbidden)

    def test_it_reads_the_lifecycle_asof_not_a_new_source(self):
        """No second notion of as-of · the row and the column agree."""
        src = (_ROOT / "backend" / "delivery" / "sheets"
               / "workbook_two.py").read_text(encoding="utf-8")
        assert '_days_held(row.get("entry_date"), d.get("asof"))' in src, (
            "the as-of must come from the lifecycle dict the sheet is "
            "already rendered from")
