"""The recommendation snapshot archive must prove it landed.

CEO 2026-11-03 · reports/recommendations_history/india/ holds two files,
both from 2026-07-29 and 2026-07-30. Nothing archived for three months,
and test_date_consistency has been failing on it.

The writer was never missing. `archive_snapshot` is called from
ssot/run.py - but it sat INSIDE a try whose handler reads "Enrichment
failure must NEVER break the SSoT pipeline · log and continue". Any
enrichment step raising before the archive line skipped the archive, the
handler printed, the step exited 0, and the orchestrator recorded

    recommendation_ssot  verdict=SUCCESS  optional=False  elapsed=3.41

for the 2026-11-02 run - a non-optional step reporting success on a day
whose snapshot was never written. The same shape as the daily-history
defect, in a second mechanism.

tmp_path-isolated. No live history directory is read or written.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.recommendation.snapshot.store import (
    archive_and_record, archive_snapshot, archive_state_path,
    list_snapshot_dates)

_ROOT = Path(__file__).resolve().parents[2]


def _payload(asof="2026-11-03", n=3, market="india"):
    return {"asof": asof, "market": market,
            "recommendations": [{"ticker": "T%02d" % i, "action": "HOLD"}
                                for i in range(n)]}


class TestArchiveAndRecord:
    def test_a_successful_archive_is_persisted_and_verified(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        st = archive_and_record(_payload(), reports, "india")
        assert st["state"] == "PERSISTED"
        assert st["verified"] is True
        assert st["n_recommendations"] == 3
        assert Path(st["path"]).exists()

    def test_persisted_requires_a_successful_readback(self, tmp_path):
        """Writing is not the same as having written."""
        reports = tmp_path / "reports"
        reports.mkdir()
        st = archive_and_record(_payload(), reports, "india")
        back = json.loads(Path(st["path"]).read_text(encoding="utf-8"))
        assert back["snapshot_asof"] == "2026-11-03"
        assert len(back["recommendations"]) == 3

    def test_a_blocked_history_directory_is_reported_failed(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        (reports / "recommendations_history").write_text("blocker",
                                                         encoding="utf-8")
        st = archive_and_record(_payload(), reports, "india")
        assert st["state"] == "FAILED"
        assert st["verified"] is False
        assert st["reason"]

    def test_the_state_file_is_written_either_way(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        archive_and_record(_payload(), reports, "india")
        p = archive_state_path(reports, "india")
        assert p.exists()
        assert json.loads(p.read_text(encoding="utf-8"))["state"] == "PERSISTED"

    def test_a_failed_archive_still_records_its_verdict(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        (reports / "recommendations_history").write_text("x", encoding="utf-8")
        archive_and_record(_payload(), reports, "india")
        st = json.loads(
            archive_state_path(reports, "india").read_text(encoding="utf-8"))
        assert st["state"] == "FAILED"
        assert st["reason"]

    def test_the_asof_comes_from_the_argument_over_the_payload(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        st = archive_and_record(_payload(asof="2026-11-02"), reports, "india",
                               asof="2026-11-03")
        assert st["asof"] == "2026-11-03"
        assert Path(st["path"]).name == "2026-11-03.json"

    def test_markets_do_not_collide(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        archive_and_record(_payload(n=2), reports, "india")
        archive_and_record(_payload(n=5), reports, "usa")
        assert list_snapshot_dates(reports, "india") == [date(2026, 11, 3)]
        assert list_snapshot_dates(reports, "usa") == [date(2026, 11, 3)]
        i = json.loads(archive_state_path(reports, "india").read_text("utf-8"))
        u = json.loads(archive_state_path(reports, "usa").read_text("utf-8"))
        assert (i["n_recommendations"], u["n_recommendations"]) == (2, 5)

    def test_rerunning_the_same_date_is_idempotent(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        a = archive_and_record(_payload(n=3), reports, "india")
        b = archive_and_record(_payload(n=3), reports, "india")
        assert a["path"] == b["path"]
        assert list_snapshot_dates(reports, "india") == [date(2026, 11, 3)]

    def test_an_empty_recommendation_list_still_archives(self, tmp_path):
        """A day with no picks is still a day that must be on the record."""
        reports = tmp_path / "reports"
        reports.mkdir()
        st = archive_and_record(_payload(n=0), reports, "india")
        assert st["state"] == "PERSISTED"
        assert st["n_recommendations"] == 0


class TestTheArchiveNoLongerDependsOnEnrichment:
    @staticmethod
    def _code_only(path: Path) -> str:
        out = []
        for line in path.read_text(encoding="utf-8",
                                   errors="replace").splitlines():
            if line.strip().startswith("#"):
                continue
            out.append(line.split("#", 1)[0] if "#" in line else line)
        return "\n".join(out)

    def test_the_runner_attempts_the_archive_outside_the_enrichment_try(self):
        src = self._code_only(_ROOT / "backend/recommendation/ssot/run.py")
        assert "snap_path = None" in src, (
            "the sentinel that lets a post-enrichment attempt know whether "
            "the archive already happened")
        assert "archive_and_record" in src
        # The post-enrichment attempt must sit after the handler that used
        # to swallow the archive.
        handler = src.index("enrichment failed")
        attempt = src.index("archive_and_record")
        assert attempt > handler, (
            "the archive attempt must come AFTER the enrichment handler, "
            "or an enrichment failure still costs the history")

    def test_a_failed_archive_is_announced_not_silent(self):
        src = self._code_only(_ROOT / "backend/recommendation/ssot/run.py")
        assert "ARCHIVE FAILED" in src

    def test_the_idempotency_lock_is_still_in_place(self):
        """The 2026-07-30 post-mortem guard must survive this change."""
        src = self._code_only(_ROOT / "backend/recommendation/ssot/run.py")
        assert "snap_existing.exists() and not args.force" in src
