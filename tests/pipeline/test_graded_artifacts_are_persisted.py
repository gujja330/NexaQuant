"""If CI grades an artifact, CI must also commit it.

CEO 2026-10-28 · A gate that reads a file the run then deletes produces a
verdict nobody can check.

Measured on origin/main 2026-10-28, after a run whose integrity gate had
just graded these files at `asof 2026-10-28 · age_days 0`:

    reports/sized_positions.json   asof 2026-09-03  run_utc 2026-09-03T08:30:56
    reports/risk_report.json       asof 2026-09-03  run_utc 2026-09-03T08:30:56
    reports/portfolio_v3.json      asof 2026-09-03  run_utc 2026-09-03T08:30:58
    reports/portfolio_state.json   asof 2026-09-03  run_utc None

All four carried the SAME September stamp, so the repository looked like
the sizing layer had frozen 55 days earlier. It had not - the pipeline
built a fresh set every morning, uploaded it, and threw it away. They
were in the upload-artifact list and in nobody's `git add`.

Uploading is not persistence here: this repository returns 403 on Actions
logs and artifacts, so an upload-only file is unreadable by anyone,
including the operator trying to find out why 0 positions were sized.

The rule this encodes: REQUIRED in scripts/ci_artifact_integrity.py is the
list of artifacts the run asserts something about. Every one of them has
to survive the run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"


def _workflow_text(name: str) -> str:
    p = WORKFLOWS / name
    assert p.exists(), "%s is missing" % name
    return p.read_text(encoding="utf-8")


def _committed_paths(text: str) -> set:
    """Paths the workflow stages, via `git add` or `_add_safe`."""
    out = set()
    for m in re.finditer(r"(?:git add|_add_safe)\s+\"?([^\"\s]+)", text):
        for tok in m.group(1).split():
            out.add(tok.strip('"'))
    # `git add a b` form · catch trailing operands on the same line
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("git add "):
            for tok in s[len("git add "):].split():
                if tok.startswith("reports/") or tok.startswith("usa/"):
                    out.add(tok)
    return out


def _required_for(market: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_cai", REPO / "scripts" / "ci_artifact_integrity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [r["path"] for r in mod.REQUIRED.get(market, [])], mod


def test_every_graded_india_artifact_is_committed():
    required, _ = _required_for("india")
    assert required, "the india REQUIRED list is empty"
    staged = _committed_paths(_workflow_text("aegis-daily.yml"))
    missing = [p for p in required if p not in staged]
    assert not missing, (
        "aegis-daily grades these and commits none of them: %s · the repo "
        "then shows a stale copy while the real output is deleted with the "
        "runner, and this repo 403s on Actions artifacts so the uploaded "
        "copy cannot be read either" % missing)


def test_the_integrity_report_itself_is_committed():
    """The verdict has to outlive the run that produced it."""
    staged = _committed_paths(_workflow_text("aegis-daily.yml"))
    assert "reports/context/artifact_integrity_india.json" in staged, (
        "the integrity verdict is not committed · it was upload-only, and "
        "an unreadable verdict is not evidence")


@pytest.mark.parametrize("path", [
    "reports/context/why_not_current_india.json",
    "reports/context/wave_regression_india.json",
    "reports/context/cil_run_india.json",
])
def test_contract_runner_outputs_are_committed_india(path):
    """why_not_current explains NEW=0 · it was rebuilt daily and dropped."""
    staged = _committed_paths(_workflow_text("aegis-daily.yml"))
    assert path in staged, "%s is produced every run and never staged" % path


@pytest.mark.parametrize("path", [
    "reports/context/why_not_current_usa.json",
    "reports/context/wave_regression_usa.json",
    "reports/context/cil_run_usa.json",
])
def test_contract_runner_outputs_are_committed_usa(path):
    staged = _committed_paths(_workflow_text("aegis-usa.yml"))
    assert path in staged, "%s is produced every run and never staged" % path


def test_guard_can_fail_when_a_required_path_is_unstaged():
    """The check must bite · otherwise it is decoration.

    Feed it a REQUIRED entry the workflow certainly does not stage and
    confirm the same comparison reports it missing.
    """
    staged = _committed_paths(_workflow_text("aegis-daily.yml"))
    fake = "reports/this_artifact_is_never_staged_by_any_workflow.json"
    assert fake not in staged
    missing = [p for p in ["reports/sized_positions.json", fake]
               if p not in staged]
    assert missing == [fake], (
        "the staged-path parser is not discriminating · it reported %r "
        "rather than just the unstaged path" % missing)


def test_the_parser_actually_finds_real_entries():
    """Guard against a regex that silently matches nothing.

    If _committed_paths returned an empty set every assertion above would
    pass vacuously, which is the failure mode this file exists to stop.
    """
    staged = _committed_paths(_workflow_text("aegis-daily.yml"))
    assert len(staged) > 10, (
        "only %d staged paths parsed out of aegis-daily.yml · the parser "
        "is broken and every test here is passing vacuously" % len(staged))
    assert "reports/portfolio_history.parquet" in staged
