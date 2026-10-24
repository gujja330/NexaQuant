"""Guard: the DATA_READY feature_snapshot gate must have a PRODUCER.

The defect this protects against is not a crash. It is a gate that is
correct, enforced, and impossible to satisfy:

  readiness.SOURCE_BUDGETS["feature_snapshot"] == 0   (today's features)
  but nothing in the USA workflow wrote features/usa/<date>.parquet

USA failed DATA_READY on this from 2026-09-09 - the last run
certification committed by hand, with `--refresh`, which built the
snapshot as a side effect - until 2026-10-24. Nothing crashed. The gate
simply reported SOURCE_STALE:FEATURE_SNAPSHOT every morning, and
because CI never committed the certification, the reason was never read.

THE TWO MARKETS REACH IT DIFFERENTLY, AND THAT IS DELIBERATE
------------------------------------------------------------
  india - india/feature_store/run.py calls build_and_persist directly
          and is a step of scripts/aegis_daily_v2.py with optional=False.
          A producer already existed. A second one in the workflow would
          duplicate the work and could satisfy the gate on a run where
          that non-optional step had FAILED, which is worse than useless.

  usa   - usa/research/feature_store/run.py is a different artifact
          despite the matching name: it writes only
          usa/reports/feature_store_summary.json. No producer existed, so
          the workflow runs scripts/ci_build_feature_snapshot.py.

So these tests assert the INVARIANT - each market has a producer that
runs before the gate - not a particular spelling of it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = {
    "usa": ROOT / ".github" / "workflows" / "aegis-usa.yml",
    "india": ROOT / ".github" / "workflows" / "aegis-daily.yml",
}

BUILDER = "scripts/ci_build_feature_snapshot.py"


def _steps(path: Path) -> list:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for job in doc["jobs"].values():
        out.extend(job.get("steps") or [])
    return out


def _index_of(steps: list, needle: str) -> int:
    for i, s in enumerate(steps):
        if needle in (s.get("run") or ""):
            return i
    return -1


def test_builder_script_exists():
    assert (ROOT / BUILDER).exists(), (
        "%s is USA's only producer of features/usa/<date>.parquet. Without "
        "it the zero-day gate can never pass." % BUILDER)


def test_usa_builds_the_snapshot_before_it_gates_on_it():
    steps = _steps(WORKFLOWS["usa"])
    build = _index_of(steps, BUILDER)
    gate = _index_of(steps, "backend.pipeline.contract.runner")
    assert gate >= 0, "usa no longer runs the contract gate"
    assert build >= 0, (
        "usa gates DATA_READY on feature_snapshot (budget 0 days) but has no "
        "step running %s. The gate is unsatisfiable." % BUILDER)
    assert build < gate, (
        "usa builds the feature snapshot at step %d, AFTER the contract gate "
        "at step %d. The gate would read yesterday's snapshot."
        % (build, gate))
    assert "--market usa" in steps[build]["run"]


def test_india_producer_is_the_orchestrator_not_a_duplicate():
    """India must have a producer, and must NOT have a second one."""
    import re
    src = (ROOT / "india" / "feature_store" / "run.py").read_text(
        encoding="utf-8")
    assert "build_and_persist" in src, (
        "india/feature_store/run.py no longer persists a snapshot - India "
        "now has NO producer and the gate becomes unsatisfiable, exactly as "
        "USA's was.")

    orch = (ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    at = orch.find('"script":   "india/feature_store/run.py"')
    if at < 0:
        at = orch.find('"script": "india/feature_store/run.py"')
    assert at >= 0, "india/feature_store/run.py is not a step of aegis_daily_v2"
    # the declaration block, up to the start of the next step
    nxt = orch.find('"name":', at)
    step_src = orch[at:nxt if nxt > at else at + 1200]
    assert '"optional": False' in step_src, (
        "the India feature_store step became optional - a silent failure "
        "would leave yesterday's snapshot and the gate would not notice")

    assert _index_of(_steps(WORKFLOWS["india"]), BUILDER) == -1, (
        "India gained a second snapshot builder in its workflow. It already "
        "has one via aegis_daily_v2. A duplicate could satisfy the gate on a "
        "run where the non-optional producer had failed.")


def test_zero_day_budget_is_still_the_rule():
    """If the budget is ever loosened, this guard's premise changes.

    Loosening it would be the 'manufacture readiness by lowering the gate'
    move, so the test names it rather than silently passing.
    """
    from backend.pipeline.contract.readiness import SOURCE_BUDGETS
    assert SOURCE_BUDGETS["feature_snapshot"] == 0, (
        "feature_snapshot budget is no longer 0 days. If that was a "
        "deliberate CEO decision, update this guard. If it was done to make "
        "CI green, revert it.")
