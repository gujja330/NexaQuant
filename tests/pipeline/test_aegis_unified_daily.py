from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.aegis_shadow.daily import _artifacts, _missing_sessions, _plan, _resume_report, _reuse_blockers, run_daily
from scripts.aegis_shadow.identity import dependencies, sync_dependencies
from scripts.aegis_shadow.pipeline import Stage
from scripts.aegis_shadow.publication import SCHEMA
from scripts.aegis_shadow.recover_daily import annotate_lifecycle


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("market", ("india", "usa"))
def test_executable_plan_resolves_engines_and_orders_certification(market):
    plan = _plan(ROOT, market, "2026-11-26")
    names = [stage.name for stage in plan]
    for producer, consumer in (
        ("session_checkpoint", "registry"), ("registry", "dynamic_risk"),
        ("dynamic_risk", "dynamic_exits"), ("dynamic_exits", "canonical_lifecycle"),
        ("canonical_lifecycle", "recovery_provenance"), ("backend_validation", "history_integrity"),
        ("history_integrity", "workbook"), ("workbook", "certify"),
    ):
        assert names.index(producer) < names.index(consumer)
    assert "telegram" not in names
    assert "multi_layer_forward_outcomes" in names
    assert names[0] == "session_checkpoint"
    if market == "usa":
        assert {"research_market_regime", "multi_layer_momentum_ledger", "multi_layer_stress_regime",
                "multi_layer_crash_resilience", "multi_layer_runner_usa"}.issubset(names)


def test_cache_reuse_checks_dependency_and_publication_versions():
    asof, session = "2026-11-26", "2026-11-25"
    current = {"source_config": {"configs/risk_budget.yaml": "a"}, "market_inputs": {}}
    publication = dict(runner="new", market="usa", workbook="report.xlsx", schema=SCHEMA,
                       asof=asof, market_data_asof=session, sha256="attachment")
    saved = dict(publication, dependencies=current, passed_stages=42, workbook_sha256="attachment")
    assert not _reuse_blockers(saved, publication, current, asof, session, False)
    assert _reuse_blockers(saved, publication, current, asof, session, True) == ["forced recomputation"]
    changed = dict(current, source_config={"configs/risk_budget.yaml": "b"})
    assert "configs/risk_budget.yaml" in _reuse_blockers(saved, publication, changed, asof, session, False)[0]
    assert _reuse_blockers(saved, dict(publication, schema="old"), current, asof, session, False)


def test_private_attempt_adopts_live_code_without_overwriting_registry(tmp_path):
    root, work = tmp_path / "live", tmp_path / "private"
    for directory, version in ((root, "live"), (work, "private")):
        (directory / "backend").mkdir(parents=True)
        (directory / "backend/risk.py").write_text(version, encoding="utf-8")
        (directory / "reports/research").mkdir(parents=True)
        (directory / "reports/research/opportunity_registry.jsonl").write_text(version, encoding="utf-8")
    old = dependencies(work, "usa")
    live = dependencies(root, "usa")
    (root / "README.md").write_text("documentation edit", encoding="utf-8")
    assert dependencies(root, "usa") == live
    india = dependencies(root, "india")
    (root / "usa/scripts").mkdir(parents=True)
    (root / "usa/scripts/build_universe.py").write_text("usa engine edit", encoding="utf-8")
    assert dependencies(root, "india") == india
    assert dependencies(root, "usa") != live
    live = dependencies(root, "usa")
    sync_dependencies(root, work, "usa", live, old)
    assert (work / "backend/risk.py").read_text(encoding="utf-8") == "live"
    assert (work / "reports/research/opportunity_registry.jsonl").read_text(encoding="utf-8") == "private"


def test_new_both_continues_to_second_market_after_failure(tmp_path, monkeypatch):
    seen = []

    def run_market(root, storage, market, *, force):
        seen.append((market, force))
        if market == "india":
            raise ValueError("fixture failure")
        return True

    monkeypatch.setattr("scripts.aegis_shadow.daily._run_market", run_market)
    assert run_daily(tmp_path, ("india", "usa"), force=True) == 1
    assert seen == [("india", True), ("usa", True)]


def test_verified_late_checkpoint_can_resume_or_rebuild_workbook(tmp_path, monkeypatch):
    private = tmp_path / ".aegis-local/unified/daily/usa"
    work = private / "attempt/work"
    work.mkdir(parents=True)
    receipt = private / "report-ready.json"
    asof, session = "2026-11-26", "2026-11-25"
    identity = {"source_config": {}, "market_inputs": {}}
    retained = dict(market="usa", asof=asof, session=session, dependencies=identity,
                    workspace="attempt/work", baseline_workspace=None, bootstrap_state={},
                    state={"artifact": "checksum"}, private_source={},
                    stages={"engine": {"status": "PASS"}}, report_context={})
    receipt.write_text(json.dumps(retained), encoding="utf-8")
    monkeypatch.setattr("scripts.aegis_shadow.daily._report_state", lambda *_: retained["state"])
    monkeypatch.setattr("scripts.aegis_shadow.daily._plan", lambda *_: tuple(
        Stage(name, lambda _: None) for name in ("engine", "workbook", "certify")))
    resumed = _resume_report(tmp_path, private, receipt, identity, {}, "usa", asof, session, None)
    assert resumed[0]["mode"] == "RESUME"
    saved = {"workspace": "attempt/work"}
    repaired = _resume_report(tmp_path, private, receipt, identity, saved, "usa", asof, session, None)
    assert repaired[0]["mode"] == "REPORT_ONLY"
    monkeypatch.setattr("scripts.aegis_shadow.daily._report_state", lambda *_: {"artifact": "changed"})
    assert _resume_report(tmp_path, private, receipt, identity, saved, "usa", asof, session, None) is None


def test_recovered_simulation_does_not_publish_a_realized_fill(tmp_path):
    context = tmp_path / "reports/context"
    context.mkdir(parents=True)
    lifecycle = context / "canonical_lifecycle_usa.json"
    lifecycle.write_text(json.dumps({"exits": [{"position_id": "episode", "exit_date": "2026-11-25",
                         "realized_pnl_pct": 5.0, "exit_price": 105.0}]}), encoding="utf-8")
    event = dict(opportunity_id="episode", session="2026-11-25", detected_utc="2026-11-26T00:00:00Z",
                 execution_status="UNKNOWN", trigger_close=105.0, policy_version="reviewed-v1")
    (context / "shadow_recovery_events_usa.json").write_text(json.dumps([event]), encoding="utf-8")
    annotate_lifecycle({"work": tmp_path, "market": "usa"})
    row = json.loads(lifecycle.read_text(encoding="utf-8"))["exits"][0]
    assert row["record_type"] == "SIMULATED OBSERVATION"
    assert row["observation_price"] == 105.0
    assert row["realized_pnl_pct"] is None
    assert row["exit_price"] is None


def test_missed_sessions_exclude_thanksgiving_weekend_and_latest_session():
    assert _missing_sessions("usa", date(2026, 11, 25), date(2026, 11, 30)) == ["2026-11-27"]
    assert _missing_sessions("india", date(2026, 11, 23), date(2026, 11, 26)) == ["2026-11-25"]


def test_artifact_contract_rejects_parent_paths_and_empty_output(tmp_path):
    artifact = tmp_path / "report_2026-11.json"
    artifact.touch()
    assert not _artifacts(tmp_path, ("report_{month}.json",), "2026-11-26")
    artifact.write_bytes(b"{}")
    assert _artifacts(tmp_path, ("report_{month}.json",), "2026-11-26") == {artifact}
    with pytest.raises(ValueError, match="invalid artifact"):
        _artifacts(tmp_path, ("../protected",), "2026-11-26")


def test_engine_worker_rejects_external_write_and_launch(tmp_path):
    work = tmp_path / "work"
    worker = work / "scripts/aegis_shadow/worker.py"
    worker.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/aegis_shadow/worker.py", worker)
    outside = tmp_path / "protected.txt"
    outside.write_text("unchanged", encoding="utf-8")
    (work / "fixture.py").write_text(
        "from pathlib import Path\n"
        "import subprocess, sys\n"
        "try:\n"
        "    Path(sys.argv[1]).write_text('wrong')\n"
        "except PermissionError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('external write succeeded')\n"
        "try:\n"
        "    subprocess.run([sys.executable, '-c', 'pass'])\n"
        "except PermissionError:\n"
        "    Path('inside.txt').write_text('allowed')\n"
        "else:\n"
        "    raise AssertionError('external launch succeeded')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(worker), "fixture.py", str(outside)],
        cwd=work, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert outside.read_text(encoding="utf-8") == "unchanged"
    assert (work / "inside.txt").read_text(encoding="utf-8") == "allowed"
