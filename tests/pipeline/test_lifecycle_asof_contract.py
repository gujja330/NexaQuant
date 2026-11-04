"""An artifact that cannot date itself cannot be checked. CEO 2026-11-04 · §F.

WHAT WENT WRONG
---------------
`reports/recommendation_lifecycle.json` has TWO writers with
incompatible schemas:

  backend/recommendation/lifecycle/run.py      asof, records, by_ticker
  research/institutional_memory/lib/lifecycle  run_utc, by_state, win_rate

Two products, one path. Measured on 2026-11-04 the two markets were
written by DIFFERENT producers:

  india  reports/recommendation_lifecycle.json      asof 2026-07-29  (engine)
  usa    usa/reports/recommendation_lifecycle.json  no asof          (research)

`test_date_consistency` reads `asof` and, when it could not parse one,
recorded a WARNING and skipped. So the research writer omitting `asof`
is what kept that check quiet over an artifact 98 days stale - and USA
was never checked at all. The check passed by accident, and which
accident depended on whichever engine wrote last.

Two fixes, both covered here:

  1. the research summary now emits `asof`, derived from the archive's
     newest day - the data's own as-of, not the wall clock, and None
     when nothing is archived rather than a fabricated date;
  2. the consistency check FAILS CLOSED on a file that exists but
     cannot be dated. Absence stays a warning, because absence can be
     legitimate; an undateable present file cannot be.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]


class TestTheResearchSummaryEmitsAsof:
    @staticmethod
    def _summarize(days, rows):
        """Run the REAL build_summary() in a subprocess rooted at the repo.

        `import research.institutional_memory...` fails under pytest:
        the repository has BOTH `research/` and `tests/research/`, and
        pytest's prepend import mode puts `tests/` on sys.path, so
        top-level `research` resolves to the TEST directory and shadows
        the real package. Another name collision, in the import system
        this time.

        A subprocess rooted at the repo resolves it correctly, so this
        exercises the shipped code rather than a re-exec'd copy of it.
        """
        lines = [
            "import json, sys",
            "sys.path.insert(0, %r)" % str(_ROOT),
            "import pandas as pd",
            "import research.institutional_memory.lib.lifecycle as L",
            "L._archive.list_archive_days = lambda: %r" % (list(days),),
            "rows = %r" % (list(rows),),
            "df = pd.DataFrame(rows) if rows else pd.DataFrame()",
            "print(json.dumps(L.build_summary(df), default=str))",
        ]
        r = subprocess.run([sys.executable, "-c", "\n".join(lines)],
                           cwd=str(_ROOT), capture_output=True, text=True,
                           timeout=180)
        assert r.returncode == 0, r.stderr[-700:]
        return json.loads(r.stdout.strip().splitlines()[-1])

    _ROW = {"ticker": "TCS", "state": "ACTIVE", "realized_return": None,
            "first_seen_date": "2026-10-30", "days_active": 4}

    def test_asof_is_the_archives_newest_day_not_today(self):
        out = self._summarize(["2026-10-30", "2026-11-03"], [self._ROW])
        assert out["asof"] == "2026-11-03"
        assert out["asof"] != date.today().isoformat(), (
            "the as-of must come from the DATA, not the wall clock")

    def test_an_empty_frame_still_carries_asof(self):
        out = self._summarize(["2026-11-03"], [])
        assert out["asof"] == "2026-11-03"
        assert out["n_total"] == 0

    def test_nothing_archived_gives_none_not_a_fabricated_date(self):
        out = self._summarize([], [])
        assert out["asof"] is None, (
            "with no archive there is no as-of · inventing one would make "
            "an empty artifact look current")

    def test_asof_is_json_serialisable_and_parseable(self):
        out = self._summarize(["2026-11-03"], [])
        assert date.fromisoformat(str(out["asof"])[:10]) == date(2026, 11, 3)


class TestTheConsistencyCheckFailsClosed:
    """The reader half of the contract."""

    @staticmethod
    def _check(tmp_path, monkeypatch, recs_asof, upstream: dict):
        import backend.tests.test_date_consistency as DC
        monkeypatch.setattr(DC, "_ROOT", tmp_path)
        rp = tmp_path / "reports"
        rp.mkdir(parents=True, exist_ok=True)
        (rp / "recommendations.json").write_text(
            json.dumps({"asof": recs_asof}), encoding="utf-8")
        for name, payload in upstream.items():
            if payload is None:
                continue
            (rp / name).write_text(json.dumps(payload), encoding="utf-8")
        return DC._check_market("india")

    def test_a_present_file_with_no_asof_is_an_ERROR(self, tmp_path,
                                                      monkeypatch):
        """The exact defect · this used to be a warning and skip."""
        errors, warnings = self._check(
            tmp_path, monkeypatch, "2026-11-04",
            {"recommendation_lifecycle.json": {"run_utc": "2026-11-03T22:00:00Z",
                                               "n_total": 5}})
        joined = " ".join(errors)
        assert "lifecycle" in joined and "no parseable" in joined, errors
        assert not any("unparseable asof" in w for w in warnings)

    def test_an_absent_file_remains_a_warning(self, tmp_path, monkeypatch):
        """Absence can be legitimate · it must not fail the run."""
        errors, warnings = self._check(
            tmp_path, monkeypatch, "2026-11-04",
            {"recommendation_lifecycle.json": None})
        assert not [e for e in errors if "lifecycle" in e]
        assert any("lifecycle missing" in w for w in warnings)

    def test_a_stale_asof_is_still_an_error(self, tmp_path, monkeypatch):
        errors, _ = self._check(
            tmp_path, monkeypatch, "2026-11-04",
            {"recommendation_lifecycle.json": {"asof": "2026-07-29"}})
        assert any("BEHIND" in e for e in errors), errors

    def test_a_current_asof_passes(self, tmp_path, monkeypatch):
        errors, _ = self._check(
            tmp_path, monkeypatch, "2026-11-04",
            {"recommendation_lifecycle.json": {"asof": "2026-11-04"}})
        assert not [e for e in errors if "lifecycle" in e], errors

    def test_a_future_dated_asof_is_an_error(self, tmp_path, monkeypatch):
        future = (date(2026, 11, 4) + timedelta(days=30)).isoformat()
        errors, _ = self._check(
            tmp_path, monkeypatch, "2026-11-04",
            {"recommendation_lifecycle.json": {"asof": future}})
        assert any("FUTURE-DATED" in e for e in errors), errors

    def test_a_non_date_asof_fails_closed_rather_than_crashing(self, tmp_path,
                                                                monkeypatch):
        errors, _ = self._check(
            tmp_path, monkeypatch, "2026-11-04",
            {"recommendation_lifecycle.json": {"asof": "not-a-date"}})
        assert any("no parseable" in e for e in errors), errors


class TestTheSharedPathIsRecorded:
    def test_both_writers_are_documented_as_sharing_one_path(self):
        """The architectural defect stays visible until it is fixed."""
        src = (_ROOT / "research" / "institutional_memory" / "lib"
               / "lifecycle.py").read_text(encoding="utf-8")
        assert "recommendation_lifecycle.json" in src
        assert "Two products, one path" in src, (
            "the path collision must stay documented at the writer")
