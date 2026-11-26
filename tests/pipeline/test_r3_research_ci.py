"""The R3 research CI must tell the truth about what it did.

CEO 2026-10-28 · Five terminal states, and the dangerous one is
PERSISTENCE_FAILURE: a run that computes decisions and fails to write
them must exit NON-ZERO. If it exits 0 the research ledger silently
loses observations while the workflow reads green - the same shape as the
five consecutive guard-skipped runs that left artifact persistence
unverified for days.

Each state is tested by driving the runner into it, not by reading the
source. All fixtures are tmp_path trees; nothing here touches the live
ledgers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

import importlib.util

REPO = Path(__file__).resolve().parents[2]
WF = REPO / ".github" / "workflows" / "aegis-r3-research.yml"


def _runner():
    spec = importlib.util.spec_from_file_location(
        "_r3ci", REPO / "scripts" / "ci_r3_research_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snapshot(root: Path, market: str, asof: str, n: int = 60):
    df = pd.DataFrame({"ticker": ["T%03d" % i for i in range(n)],
                       "ensemble_score": [float(n - i) for i in range(n)]})
    p = root / "history" / market / asof / "r2_scores.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def _coverage_rows(root: Path, market: str):
    from backend.research.r3_program.shadow_recommender import coverage_path
    p = coverage_path(root, market)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


# ── state classification ─────────────────────────────────────────────
def test_upstream_failure_is_a_guard_skip_not_an_observation(tmp_path):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    p = m.run_market(tmp_path, "india", upstream_conclusion="failure")
    assert p["terminal_state"] == "SKIPPED_BY_GUARD"
    assert p["is_research_observation"] is False, (
        "an upstream failure was counted as a research observation")
    assert "UPSTREAM_FAILURE" in p["reason"]
    # and it must NOT have written any decisions
    from backend.research.r3_program.shadow_recommender import ledger_path
    assert not ledger_path(tmp_path, "india").exists()


@pytest.mark.parametrize("conclusion",
                         ["failure", "cancelled", "timed_out", "skipped"])
def test_every_non_success_upstream_is_skipped(tmp_path, conclusion):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    p = m.run_market(tmp_path, "india", upstream_conclusion=conclusion)
    assert p["terminal_state"] == "SKIPPED_BY_GUARD"
    assert conclusion.upper() in p["reason"]


def test_no_sealed_snapshot_is_zero_coverage_not_failure(tmp_path):
    m = _runner()
    p = m.run_market(tmp_path, "india")
    assert p["terminal_state"] == "ZERO_COVERAGE_OK"
    assert p["reason"] == "NO_SEALED_SNAPSHOT"
    assert p["is_research_observation"] is False


def test_first_run_records(tmp_path):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    p = m.run_market(tmp_path, "india")
    assert p["terminal_state"] == "RECORDED"
    assert p["is_research_observation"] is True
    assert p["decided"] > 0
    assert p["rows_after"] > p["rows_before"]
    assert "UNVALIDATED" in p["validation_status"]


def test_second_run_on_the_same_snapshot_is_not_duplicated(tmp_path):
    """Duplicate protection · idempotent by content, not by schedule."""
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    first = m.run_market(tmp_path, "india")
    assert first["terminal_state"] == "RECORDED"
    second = m.run_market(tmp_path, "india")
    assert second["terminal_state"] == "ZERO_COVERAGE_OK"
    assert second["reason"] == "ALL_SEALED_DATES_ALREADY_PROCESSED"
    assert second["is_research_observation"] is False
    from backend.research.r3_program.shadow_recommender import (
        ledger_path, _read_jsonl)
    rows = _read_jsonl(ledger_path(tmp_path, "india"))
    ids = [r["decision_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate decisions were written"


def test_a_policy_version_bump_reopens_every_sealed_date(tmp_path,
                                                         monkeypatch):
    """The defect this closes · duplicate identity keyed on as_of alone.

    decision_id includes the engine version, so a policy bump makes
    genuinely new decisions. Keying duplicate protection on as_of alone
    returned ALL_SEALED_DATES_ALREADY_PROCESSED before sr.run() was ever
    called, so a v2 policy recorded NOTHING, permanently, while the
    workflow reported green.
    """
    m = _runner()
    from backend.research.r3_program import shadow_recommender as sr
    _snapshot(tmp_path, "india", "2026-01-05")

    assert m.run_market(tmp_path, "india")["terminal_state"] == "RECORDED"
    again = m.run_market(tmp_path, "india")
    assert again["terminal_state"] == "ZERO_COVERAGE_OK", (
        "same policy re-ran · de-duplication within a policy is broken")

    monkeypatch.setattr(sr, "ENGINE_VERSION",
                        "R3_EXPERIMENTAL_BASELINE_v2")
    bumped = m.run_market(tmp_path, "india")
    assert bumped["terminal_state"] == "RECORDED", (
        "a policy bump reported %s · the new policy would never record "
        "anything" % bumped["terminal_state"])
    rows = sr._read_jsonl(sr.ledger_path(tmp_path, "india"))
    vers = {r.get("engine_version") for r in rows}
    assert vers == {"R3_EXPERIMENTAL_BASELINE_v1",
                    "R3_EXPERIMENTAL_BASELINE_v2"}, (
        "ledger holds %s · both policies must coexist" % vers)
    ids = [r["decision_id"] for r in rows]
    assert len(ids) == len(set(ids)), "the bump duplicated decision ids"


def test_dedup_identity_includes_the_engine_version():
    """Source-level companion · the identity must not regress to as_of."""
    src = (REPO / "scripts" / "ci_r3_research_run.py").read_text(
        encoding="utf-8")
    assert 'r.get("engine_version")' in src, (
        "duplicate protection no longer considers the engine version")
    assert "(d, engine) not in done" in src


def test_execution_failure_when_decide_raises(tmp_path, monkeypatch):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    from backend.research.r3_program import shadow_recommender as sr

    def boom(*a, **k):
        raise RuntimeError("synthetic decide failure")
    monkeypatch.setattr(sr, "run", boom)
    p = m.run_market(tmp_path, "india")
    assert p["terminal_state"] == "EXECUTION_FAILURE"
    assert p["reason"] == "DECIDE_RAISED"
    assert "synthetic decide failure" in p["error"]
    assert p["is_research_observation"] is False


def test_persistence_failure_when_decisions_are_not_written(tmp_path,
                                                            monkeypatch):
    """THE critical state · computed but not persisted."""
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    from backend.research.r3_program import shadow_recommender as sr

    # claims it decided 500 rows but writes nothing
    monkeypatch.setattr(sr, "run", lambda *a, **k: {
        "recorded_this_run": 500, "dates_recorded": 1,
        "prospective_rows": 0, "prospective_dates": 0,
        "evidence_class": "EXPLORATORY"})
    p = m.run_market(tmp_path, "india")
    assert p["terminal_state"] == "PERSISTENCE_FAILURE", (
        "500 decisions vanished and the runner reported %s"
        % p["terminal_state"])
    assert p["decided"] == 500
    assert p["rows_after"] == p["rows_before"]
    assert p["is_research_observation"] is False


def test_failing_states_exit_non_zero_and_others_do_not():
    m = _runner()
    assert set(m.FAILING_STATES) == {"EXECUTION_FAILURE",
                                     "PERSISTENCE_FAILURE"}
    for ok in ("RECORDED", "ZERO_COVERAGE_OK", "SKIPPED_BY_GUARD"):
        assert ok not in m.FAILING_STATES, (
            "%s would fail the workflow · a skip is not a failure" % ok)


def test_persistence_failure_makes_main_exit_non_zero(tmp_path,
                                                      monkeypatch):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    from backend.research.r3_program import shadow_recommender as sr
    monkeypatch.setattr(sr, "run", lambda *a, **k: {
        "recorded_this_run": 7, "dates_recorded": 1})
    rc = m.main(["--market", "india", "--root", str(tmp_path)])
    assert rc == 1, "a lost-observation run exited 0"


def test_recorded_run_exits_zero(tmp_path):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    assert m.main(["--market", "india", "--root", str(tmp_path)]) == 0


# ── auditability ─────────────────────────────────────────────────────
@pytest.mark.parametrize("scenario", ["upstream_fail", "zero", "recorded"])
def test_every_attempt_appends_a_coverage_row(tmp_path, scenario):
    """Including failures · 'attempted and failed' must differ from
    'never ran'."""
    m = _runner()
    if scenario != "zero":
        _snapshot(tmp_path, "india", "2026-01-05")
    up = "failure" if scenario == "upstream_fail" else "success"
    rc = m.main(["--market", "india", "--root", str(tmp_path),
                 "--upstream-conclusion", up])
    rows = _coverage_rows(tmp_path, "india")
    assert rows, "no coverage row for scenario %s" % scenario
    assert rows[-1]["terminal_state"] in m.STATES
    assert "run_utc" in rows[-1]
    assert rc == 0


def test_coverage_row_written_even_on_persistence_failure(tmp_path,
                                                          monkeypatch):
    m = _runner()
    _snapshot(tmp_path, "india", "2026-01-05")
    from backend.research.r3_program import shadow_recommender as sr
    monkeypatch.setattr(sr, "run", lambda *a, **k: {"recorded_this_run": 3})
    m.main(["--market", "india", "--root", str(tmp_path)])
    rows = _coverage_rows(tmp_path, "india")
    assert rows[-1]["terminal_state"] == "PERSISTENCE_FAILURE", (
        "a failed attempt left no auditable trace")


# ── workflow contract ────────────────────────────────────────────────
def _wf():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _wf_effective() -> str:
    """The workflow with comment-only lines removed.

    Scanning the raw text is wrong and I got it wrong three times in this
    session: the comments EXPLAIN why `.published` and `reports/context`
    are excluded, so a substring scan matches the explanation and fails on
    correct code. A guard that fires on the documentation of its own rule
    teaches people to delete the documentation.
    """
    return "\n".join(l for l in WF.read_text(encoding="utf-8").splitlines()
                     if not l.strip().startswith("#"))


def test_the_comment_stripper_actually_strips():
    """Otherwise the two scans below pass vacuously."""
    raw = WF.read_text(encoding="utf-8")
    eff = _wf_effective()
    assert len(eff) < len(raw), "nothing was stripped"
    assert "data/.published" in raw, (
        "the fixture assumption is gone · the comments no longer mention "
        "the guard, so these scans prove less than they appear to")
    assert "data/.published" not in eff


def test_workflow_triggers_only_after_the_snapshot_producers():
    d = _wf()
    on = d.get("on") or d.get(True)
    assert "workflow_run" in on, (
        "a cron would race the sealing step and read a half-written "
        "snapshot")
    assert set(on["workflow_run"]["workflows"]) == {"AEGIS Daily",
                                                    "AEGIS USA"}
    assert on["workflow_run"]["types"] == ["completed"]
    assert "schedule" not in on


def test_upstream_workflow_names_actually_exist():
    """A renamed upstream would silently never trigger this."""
    names = set()
    for f in ("aegis-daily.yml", "aegis-usa.yml"):
        d = yaml.safe_load((REPO / ".github" / "workflows" / f)
                           .read_text(encoding="utf-8"))
        names.add(d["name"])
    on = _wf().get("on") or _wf().get(True)
    for w in on["workflow_run"]["workflows"]:
        assert w in names, (
            "workflow_run listens for %r but no workflow is named that · "
            "known names: %s" % (w, sorted(names)))


def test_workflow_does_not_inherit_the_published_guard():
    src = _wf_effective()
    assert "data/.published" not in src, (
        "the research ledger must receive every eligible sealed snapshot · "
        "the .published guard is a delivery concern and would drop "
        "observations on backup runs")
    assert "outputs.run == 'true'" not in src


def test_workflow_uses_least_privilege():
    d = _wf()
    assert d["permissions"] == {"contents": "write"}, (
        "permissions are %r · the job only needs to commit its own "
        "research artifacts" % d["permissions"])


def test_workflow_serialises_and_does_not_cancel_mid_write():
    d = _wf()
    assert d["concurrency"]["cancel-in-progress"] is False, (
        "cancelling mid-write is how a half-persisted ledger happens")
    assert "aegis-r3-research" in d["concurrency"]["group"]


def test_workflow_writes_only_under_the_experiment_directory():
    src = _wf_effective()
    staged = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith('"$D/') or s.startswith('"$D"'):
            staged.append(s)
    assert staged, "no explicit staged paths found"
    assert 'D=reports/research/r3/experiment' in src
    # nothing R2 owns, and no shadow ledger
    for banned in ("reports/context", "reports/telegram", "r3/shadow",
                   "data/.published", "reports/portfolio"):
        assert banned not in src, (
            "the research workflow references %s · it must write only "
            "under reports/research/r3/experiment/" % banned)
    assert "git add -A" not in src and "git add ." not in src


def test_workflow_fails_the_run_when_the_research_step_failed():
    src = _wf_effective()
    assert "steps.r3.outcome != 'success'" in src, (
        "a failed research step would read green")
    assert "exit 1" in src


def test_production_workflows_are_not_modified_by_this_change():
    """R2 isolation · the production files must not mention R3 research."""
    for f in ("aegis-daily.yml", "aegis-usa.yml"):
        src = (REPO / ".github" / "workflows" / f).read_text(encoding="utf-8")
        for probe in ("ci_r3_research_run", "aegis-r3-research",
                      "shadow_recommender", "experiment_outcomes"):
            assert probe not in src, (
                "%s references %s · the research track must not be wired "
                "into a production workflow" % (f, probe))


def test_runner_never_touches_production_modules():
    import ast
    src = (REPO / "scripts" / "ci_r3_research_run.py").read_text(
        encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
    banned = ("backend.delivery", "backend.recommendation",
              "backend.execution", "backend.portfolio")
    hits = [x for x in mods
            if any(x == b or x.startswith(b + ".") for b in banned)]
    assert not hits, "the runner imports production code: %s" % hits
