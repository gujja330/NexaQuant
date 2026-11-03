"""The learning corpus must be read as of a date, not in full.

CEO 2026-11-03 · LearningEngine.run(asof=...) re-read the entire corpus
after computing new outcomes and reported its statistics, calibration and
failure clusters from all of it. `run(asof=date(2020,1,1))` returned
n_corpus_total=2 from rows whose positions closed in August and September
2026 - six years of future information in every downstream number.

`compute_outcomes` was already point-in-time correct through `cutoff=asof`,
which is why the determinism test two cases above it passed while the
cutoff was being ignored for everything else. That is the shape of this
bug class worth remembering: the guard existed, on the other half of the
function.

tmp_path-isolated except where a test says it reads the live corpus.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend.learning.corpus import corpus_asof

_ROOT = Path(__file__).resolve().parents[2]


def _corpus(rows):
    return pd.DataFrame([{
        "market": "usa", "ticker": t, "rec_asof": r, "close_asof": c,
        "return_pct": p, "is_winner": p > 0,
    } for t, r, c, p in rows])


class TestCorpusAsof:
    def test_a_row_closing_after_asof_is_excluded(self):
        c = _corpus([("AAA", "2026-07-01", "2026-09-23", 5.0)])
        assert len(corpus_asof(c, date(2020, 1, 1))) == 0
        assert len(corpus_asof(c, date(2026, 9, 22))) == 0

    def test_a_row_closing_on_asof_is_included(self):
        """Knowable the day it closes · `<=`, not `<`."""
        c = _corpus([("AAA", "2026-07-01", "2026-09-23", 5.0)])
        assert len(corpus_asof(c, date(2026, 9, 23))) == 1

    def test_the_corpus_grows_monotonically_with_asof(self):
        c = _corpus([("AAA", "2026-07-01", "2026-08-19", -1.0),
                     ("BBB", "2026-08-01", "2026-09-23", 2.0),
                     ("CCC", "2026-09-01", "2026-10-15", 3.0)])
        counts = [len(corpus_asof(c, d)) for d in
                  (date(2026, 1, 1), date(2026, 8, 19), date(2026, 9, 23),
                   date(2026, 10, 15), date(2026, 12, 31))]
        assert counts == [0, 1, 2, 3, 3]
        assert counts == sorted(counts), "a PIT view can never shrink"

    def test_a_missing_close_date_is_excluded_not_assumed_knowable(self):
        """Keeping it would restore the leak for the least justifiable rows."""
        c = _corpus([("AAA", "2026-07-01", None, 5.0),
                     ("BBB", "2026-07-01", "2026-08-01", 1.0)])
        out = corpus_asof(c, date(2026, 12, 31))
        assert len(out) == 1 and list(out["ticker"]) == ["BBB"]

    def test_an_unparseable_close_date_is_excluded(self):
        c = _corpus([("AAA", "2026-07-01", "not-a-date", 5.0)])
        assert len(corpus_asof(c, date(2026, 12, 31))) == 0

    def test_a_corpus_without_the_column_returns_empty_not_whole(self):
        """It cannot be cut, so it cannot be trusted · fail closed."""
        c = _corpus([("AAA", "2026-07-01", "2026-08-01", 1.0)]).drop(
            columns=["close_asof"])
        out = corpus_asof(c, date(2026, 12, 31))
        assert len(out) == 0
        assert list(out.columns) == list(c.columns), "shape preserved"

    def test_an_empty_corpus_stays_empty(self):
        assert corpus_asof(pd.DataFrame(), date(2026, 1, 1)).empty
        assert corpus_asof(None, date(2026, 1, 1)).empty

    def test_a_string_asof_is_accepted(self):
        c = _corpus([("AAA", "2026-07-01", "2026-08-01", 1.0)])
        assert len(corpus_asof(c, "2026-08-01")) == 1
        assert len(corpus_asof(c, "2026-07-31")) == 0


class TestEngineHonoursAsof:
    """The regression itself, against the live corpus."""

    @staticmethod
    def _run(asof):
        from backend.learning.engine import LearningEngine
        return LearningEngine(_ROOT, "usa").run(asof=asof)

    def test_a_distant_past_asof_sees_an_empty_corpus(self):
        r = self._run(date(2020, 1, 1))
        assert r.n_corpus_total == 0, (
            "the 2026 corpus must not be visible in 2020")
        assert r.calibration_curve.method == "identity"
        assert r.n_winners == 0 and r.n_losers == 0

    def test_corpus_total_never_decreases_as_asof_advances(self):
        totals = [self._run(d).n_corpus_total for d in
                  (date(2020, 1, 1), date(2026, 8, 20), date(2026, 9, 30),
                   date(2026, 11, 3))]
        assert totals == sorted(totals), totals

    def test_todays_view_is_unchanged_by_the_fix(self):
        """The live run must still see the whole corpus.

        Every row in the live USA corpus closed before today, so the cut
        removes nothing from a current run - the fix is invisible in
        production and only bites on historical replays, which is where
        the leak was doing its damage.
        """
        from backend.learning.corpus import read_corpus
        full = read_corpus(_ROOT, "usa")
        if full.empty:
            pytest.skip("no live USA corpus in this checkout")
        today = self._run(date.today())
        assert today.n_corpus_total == len(full)
