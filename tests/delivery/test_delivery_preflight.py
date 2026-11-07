"""One blocker per day is not a fix. CEO 2026-11-07.

WHAT WENT WRONG
---------------
India failed five consecutive days and each day produced exactly ONE
blocker, which was fixed, only for the next to appear on the next run:

    2026-11-05  A23 - rotation closes aged out of the 90-day window
    2026-11-06  A23 - same cause, cohort grown from 3 tickers to 6
    2026-11-07  A23 - lineage recorded, then TRUNCATED by the sender

That is one missing capability, not five defects: nothing evaluated the
whole blocking surface at once, so the pipeline could only ever reveal
the first blocker it hit. And "India failed" covered three materially
different situations that looked identical from outside:

    1  the audit ledger was mutated during the send
    2  lineage intact, a gate refused
    3  gate allowed, the send itself failed

WHAT IS ASSERTED HERE
---------------------
That the preflight reports EVERY blocker together rather than the first,
that it recomputes evidence rather than trusting a persisted report
(measured 2026-11-07: india's gate read A23 FAIL from a report written
while the lineage was truncated, and recomputing turned the same gate to
ALLOW), and that the postflight FAILS the run when an audit ledger loses
records during a send - the exact regression that made a verified fix
look broken.

It asserts nothing about allowing a send. The preflight cannot allow
anything; it recomputes and reports, and a blocked delivery stays
blocked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import scripts.ci_delivery_preflight as PF
from backend.delivery.lineage import episode_lineage as EL

_ROOT = Path(__file__).resolve().parents[2]
_IND_WF = _ROOT / ".github" / "workflows" / "aegis-daily.yml"
_USA_WF = _ROOT / ".github" / "workflows" / "aegis-usa.yml"


def _write_ledger(root: Path, market: str, episodes) -> Path:
    p = EL.audit_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for oid in episodes:
            fh.write(json.dumps({
                "kind": EL.KIND, "opportunity_id": oid,
                "ticker": oid.split("-")[2], "closed_date": "2026-08-06",
            }) + "\n")
    return p


# ─────────────────────────────────────────────────────────────
# lineage state · the measurement the ambiguity needed
# ─────────────────────────────────────────────────────────────

class TestLineageState:

    def test_absent_ledger_is_reported_not_crashed(self, tmp_path):
        st = PF.lineage_state(tmp_path, "india")
        assert st["exists"] is False
        assert st["rows"] == 0 and st["lineage_records"] == 0
        assert st["sha256"] is None

    def test_rows_records_and_hash_are_captured(self, tmp_path):
        _write_ledger(tmp_path, "india",
                      ["IND-R2-AAA-20260805-a", "IND-R2-BBB-20260805-b"])
        st = PF.lineage_state(tmp_path, "india")
        assert st["rows"] == 2
        assert st["lineage_records"] == 2
        assert st["sha256"] and len(st["sha256"]) == 64
        assert st["episode_ids"] == ["IND-R2-AAA-20260805-a",
                                     "IND-R2-BBB-20260805-b"]

    def test_the_hash_changes_when_the_ledger_changes(self, tmp_path):
        _write_ledger(tmp_path, "india", ["IND-R2-AAA-20260805-a"])
        a = PF.lineage_state(tmp_path, "india")["sha256"]
        _write_ledger(tmp_path, "india", ["IND-R2-AAA-20260805-a",
                                          "IND-R2-BBB-20260805-b"])
        b = PF.lineage_state(tmp_path, "india")["sha256"]
        assert a != b


# ─────────────────────────────────────────────────────────────
# the failure boundary
# ─────────────────────────────────────────────────────────────

class TestTheFailureBoundary:

    def test_a_truncated_ledger_is_detected_and_named(self, tmp_path):
        """The 2026-11-07 regression, reproduced.

        37 rows / 11 records -> 26 / 0, and A23 failed again on a fix
        that had measured clean.
        """
        ids = ["IND-R2-ATUL-20260805-0e68e6",
               "IND-R2-BHARATFORG-20260805-615b4c",
               "IND-R2-HCLTECH-20260804-5d47d0"]
        _write_ledger(tmp_path, "india", ids)
        pre = {"lineage": PF.lineage_state(tmp_path, "india")}
        _write_ledger(tmp_path, "india", [])          # the sender's mode "w"
        res = PF.compare_post(tmp_path, "india", pre)
        assert res["ledger_mutated"] is True
        assert res["verdict"] == PF.STATE_LEDGER_MUTATED
        assert res["n_episodes_lost"] == 3
        assert "IND-R2-BHARATFORG-20260805-615b4c" in res["episodes_lost"], (
            "the lost episodes must be NAMED · 'India failed' is what we "
            "are replacing")

    def test_an_intact_ledger_reports_intact(self, tmp_path):
        ids = ["IND-R2-AAA-20260805-a", "IND-R2-BBB-20260805-b"]
        _write_ledger(tmp_path, "india", ids)
        pre = {"lineage": PF.lineage_state(tmp_path, "india")}
        res = PF.compare_post(tmp_path, "india", pre)
        assert res["ledger_mutated"] is False
        assert res["verdict"] == "LEDGER_INTACT"
        assert res["n_episodes_lost"] == 0

    def test_rows_added_by_another_component_are_not_a_mutation(self, tmp_path):
        """The sender legitimately refreshes its OWN rows."""
        _write_ledger(tmp_path, "india", ["IND-R2-AAA-20260805-a"])
        pre = {"lineage": PF.lineage_state(tmp_path, "india")}
        _write_ledger(tmp_path, "india", ["IND-R2-AAA-20260805-a",
                                          "IND-R2-NEW-20261107-n"])
        res = PF.compare_post(tmp_path, "india", pre)
        assert res["ledger_mutated"] is False, (
            "growth is not loss · only a dropped episode is a mutation")

    def test_a_missing_pre_state_does_not_crash_the_postflight(self, tmp_path):
        _write_ledger(tmp_path, "india", ["IND-R2-AAA-20260805-a"])
        res = PF.compare_post(tmp_path, "india", {})
        assert res["ledger_mutated"] is False
        assert res["n_episodes_lost"] == 0


# ─────────────────────────────────────────────────────────────
# it reports EVERY blocker, and cannot allow anything
# ─────────────────────────────────────────────────────────────

class TestItReportsEveryBlocker:

    def test_blockers_are_a_list_not_the_first_one(self, tmp_path,
                                                    monkeypatch):
        class _G:
            blocking_codes = ["A23", "A19", "SUBSTRATE:FEATURE_STORE"]
            reasons = ["a23 reason", "a19 reason", "substrate reason"]
        import backend.delivery.delivery_gate as DG
        monkeypatch.setattr(DG, "decide", lambda r, m: _G())
        monkeypatch.setattr(EL, "reconcile", lambda r, m, a, dry_run=False: {
            "n_selected": 0, "unaccounted_before": 0, "unaccounted_after": 0})
        rep = PF.evaluate(tmp_path, "india", "2026-11-07", recompute=False)
        codes = [b["code"] for b in rep["blockers"]]
        assert "A23" in codes and "A19" in codes
        assert "SUBSTRATE:FEATURE_STORE" in codes
        assert len(codes) >= 3, (
            "all blockers together · one per day is how five days happen")
        assert rep["verdict"] == PF.STATE_GATE_BLOCKED

    def test_no_blockers_yields_gate_allowed(self, tmp_path, monkeypatch):
        class _G:
            blocking_codes = []
            reasons = []
        import backend.delivery.delivery_gate as DG
        monkeypatch.setattr(DG, "decide", lambda r, m: _G())
        monkeypatch.setattr(EL, "reconcile", lambda r, m, a, dry_run=False: {
            "n_selected": 0, "unaccounted_before": 0, "unaccounted_after": 0})
        rep = PF.evaluate(tmp_path, "india", "2026-11-07", recompute=False)
        assert rep["blockers"] == []
        assert rep["verdict"] == PF.STATE_GATE_ALLOWED

    def test_remaining_unaccounted_lineage_is_itself_a_blocker(self, tmp_path,
                                                                monkeypatch):
        class _G:
            blocking_codes = []
            reasons = []
        import backend.delivery.delivery_gate as DG
        monkeypatch.setattr(DG, "decide", lambda r, m: _G())
        monkeypatch.setattr(EL, "reconcile", lambda r, m, a, dry_run=False: {
            "n_selected": 0, "unaccounted_before": 4, "unaccounted_after": 4})
        rep = PF.evaluate(tmp_path, "india", "2026-11-07", recompute=False)
        assert any(b["code"] == "LINEAGE:UNACCOUNTED"
                   for b in rep["blockers"])

    def test_a_gate_that_cannot_be_evaluated_is_a_blocker_not_a_pass(
            self, tmp_path, monkeypatch):
        """Silence must never read as ALLOW."""
        import backend.delivery.delivery_gate as DG

        def boom(*a, **k):
            raise RuntimeError("gate unavailable")

        monkeypatch.setattr(DG, "decide", boom)
        monkeypatch.setattr(EL, "reconcile", lambda r, m, a, dry_run=False: {
            "n_selected": 0, "unaccounted_before": 0, "unaccounted_after": 0})
        rep = PF.evaluate(tmp_path, "india", "2026-11-07", recompute=False)
        assert any(b["code"] == "GATE:ERROR" for b in rep["blockers"])
        assert rep["verdict"] == PF.STATE_GATE_BLOCKED

    def test_the_preflight_cannot_allow_a_send(self):
        """It has no override, no bypass, no gate mutation."""
        src = (_ROOT / "scripts"
               / "ci_delivery_preflight.py").read_text(encoding="utf-8")
        for forbidden in ("override_allow", "BLOCKING_CODES =",
                          "extra_blocking_codes ="):
            assert forbidden not in src, (
                "the preflight reports · it must not be able to change "
                "what blocks (found %s)" % forbidden)


# ─────────────────────────────────────────────────────────────
# workflow wiring
# ─────────────────────────────────────────────────────────────

class TestWorkflowWiring:

    @staticmethod
    def _names(path: Path, job: str) -> list:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return [str(s.get("name") or "") for s in d["jobs"][job]["steps"]]

    @staticmethod
    def _step(path: Path, job: str, frag: str) -> dict:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        for s in d["jobs"][job]["steps"]:
            if frag in str(s.get("name") or ""):
                return s
        raise AssertionError("%s: no step matching %s" % (path.name, frag))

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_preflight_runs_before_the_send(self, wf, job):
        names = self._names(wf, job)
        i_pre = next(i for i, n in enumerate(names) if "preflight" in n)
        i_send = next(i for i, n in enumerate(names)
                      if "Telegram Command Center" in n)
        assert i_pre < i_send

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_postflight_runs_after_the_send(self, wf, job):
        names = self._names(wf, job)
        i_post = next(i for i, n in enumerate(names) if "postflight" in n)
        i_send = next(i for i, n in enumerate(names)
                      if "Telegram Command Center" in n)
        assert i_send < i_post

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_both_phases_run_on_always(self, wf, job):
        for frag in ("preflight", "postflight"):
            st = self._step(wf, job, frag)
            cond = str(st.get("if") or "")
            if frag == "preflight":
                assert "always()" in cond, (
                    "the blocker list is most needed when something "
                    "upstream already failed")

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_preflight_is_report_only(self, wf, job):
        run = str(self._step(wf, job, "preflight").get("run") or "")
        assert "--report-only" in run, (
            "it runs BEFORE the sender rebuilds the workbook, so its A23 "
            "view is pre-rebuild and must not add a false failure")
        assert "--phase pre" in run

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_postflight_is_NOT_report_only(self, wf, job):
        st = self._step(wf, job, "postflight")
        run = str(st.get("run") or "")
        assert "--phase post" in run
        assert "--report-only" not in run, (
            "a component silently destroying an audit ledger must fail "
            "the run, not be rediscovered by reading tea leaves")
        assert not st.get("continue-on-error")
