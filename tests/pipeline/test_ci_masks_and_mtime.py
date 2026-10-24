"""Guards for the two masks removed on 2026-10-24.

Both hid a real failure behind something that looked like success.

  1. mtime-as-freshness. backend/ingest/pipeline_helpers.py decided
     "is this artifact fresh?" from st_mtime. actions/checkout writes
     the whole tree at job start, so in CI every file reported an age of
     seconds regardless of content, and every opted-in step was skipped
     as SUCCESS_CACHED without ever running. 3 steps in aegis_daily_v2,
     6 in usa_daily. Same class as cc72d4df.

  2. `aegis_daily_v2.py --continue || echo "(non-fatal)"`. The exit code
     was discarded, so a failed step marked optional=False - "a silent
     failure here makes the next stage score yesterday's data and look
     healthy doing it" - was indistinguishable from success. Because the
     artifacts are TRACKED, the failure left last week's committed data
     in place rather than a gap.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "ci_orchestrator_gate.py"


# ── 1 · mtime ────────────────────────────────────────────────────────
@pytest.fixture
def clean_env():
    saved = {k: os.environ.get(k)
             for k in ("GITHUB_ACTIONS", "CI", "AEGIS_TRUST_MTIME")}
    for k in saved:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v


def _fresh_file():
    fd, tp = tempfile.mkstemp()
    os.close(fd)
    p = Path(tp)
    p.write_text("x", encoding="utf-8")
    return p


def test_mtime_cache_is_disabled_in_ci(clean_env):
    """A fresh checkout makes every mtime a lie, so the cache must be off."""
    from backend.ingest.pipeline_helpers import (orchestrator_step_fresh,
                                                 staleness_skip)
    p = _fresh_file()
    try:
        assert staleness_skip(p, 20) is True, "local run keeps the speedup"
        assert orchestrator_step_fresh([str(p)], 20) is True

        for var in ("GITHUB_ACTIONS", "CI"):
            os.environ.pop("GITHUB_ACTIONS", None)
            os.environ.pop("CI", None)
            os.environ[var] = "true"
            assert staleness_skip(p, 20) is False, (
                "%s set: a brand-new mtime from actions/checkout must NOT "
                "count as freshness" % var)
            assert orchestrator_step_fresh([str(p)], 20) is False, (
                "%s set: the orchestrator must run the step" % var)
    finally:
        p.unlink(missing_ok=True)


def test_mtime_override_is_explicit_and_opt_in(clean_env):
    from backend.ingest.pipeline_helpers import staleness_skip
    p = _fresh_file()
    try:
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ["AEGIS_TRUST_MTIME"] = "1"
        assert staleness_skip(p, 20) is True, (
            "AEGIS_TRUST_MTIME=1 must restore the cache for a runner that "
            "genuinely preserves mtimes")
    finally:
        p.unlink(missing_ok=True)


# ── 2 · the orchestrator mask ────────────────────────────────────────
def _run_gate(payload, tmp_path):
    """Run the real gate against a crafted verdict, via a repo-shaped dir."""
    vp = ROOT / "reports" / "context" / "orchestrator_verdict_india.json"
    backup = vp.read_text(encoding="utf-8") if vp.exists() else None
    try:
        if payload is None:
            vp.unlink(missing_ok=True)
        else:
            vp.parent.mkdir(parents=True, exist_ok=True)
            vp.write_text(json.dumps(payload), encoding="utf-8")
        r = subprocess.run([sys.executable, str(GATE), "--market", "india"],
                           capture_output=True, text=True, cwd=str(ROOT))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    finally:
        if backup is not None:
            vp.write_text(backup, encoding="utf-8")
        else:
            vp.unlink(missing_ok=True)


def test_gate_fails_on_critical_step(tmp_path):
    code, out = _run_gate({
        "verdict": "CRITICAL_FAILURE",
        "critical_failures": [{"step": "global_context_bars",
                               "verdict": "FAILURE", "note": "yfinance 429"}],
        "optional_failures": [],
    }, tmp_path)
    assert code == 1, "a non-optional step failure must fail the run"
    assert "global_context_bars" in out, "the gate must NAME the failing step"


def test_gate_does_not_block_on_optional_step(tmp_path):
    """Trading a silent failure for a loud outage is not a fix."""
    code, out = _run_gate({
        "verdict": "DEGRADED", "critical_failures": [],
        "optional_failures": ["ingest_news_sentiment"],
    }, tmp_path)
    assert code == 0, "one flaky optional fetch must not cost the delivery"
    assert "DEGRADED" in out, "but it must still be reported"


def test_gate_fails_when_the_orchestrator_never_finished(tmp_path):
    code, out = _run_gate(None, tmp_path)
    assert code == 2, "a missing verdict means the process died · not success"


def test_workflow_runs_the_gate_after_the_orchestrator():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(
        (ROOT / ".github/workflows/aegis-daily.yml").read_text(encoding="utf-8"))
    steps = [s for j in doc["jobs"].values() for s in j["steps"]]
    runs = [s.get("run") or "" for s in steps]
    orch = next(i for i, r in enumerate(runs) if "aegis_daily_v2.py" in r)
    gate = next((i for i, r in enumerate(runs)
                 if "ci_orchestrator_gate.py" in r), -1)
    assert gate >= 0, (
        "the orchestrator mask is back: aegis_daily_v2 runs with no gate "
        "judging its verdict, so a failed non-optional step is silent again")
    assert gate > orch, "the gate must run AFTER the orchestrator"


def test_orchestrator_writes_a_verdict_ci_can_judge():
    src = (ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    assert "orchestrator_verdict_india.json" in src, (
        "aegis_daily_v2 no longer writes its verdict - the gate has nothing "
        "to read and will exit 2 on every run")
    assert "critical_failures" in src
