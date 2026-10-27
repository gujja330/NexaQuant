"""Phase E · the evidence chain must survive the run.

The artifact lifecycle audit (reports/audits/AEGIS_ARTIFACT_LIFECYCLE_AUDIT.md)
established, on 2026-10-27:

  * 99 of 138 declared artifacts had NO persistence mechanism - neither a Git
    commit nor a CI artifact. They existed only inside the runner.
  * `backend_validation` runs at orchestrator step 6 and grades artifacts
    whose producers run at steps 24-26, so it graded pre-run leftovers. Being
    unpersisted, those leftovers were permanently 2026-09-04 - the entire
    "35 datasets 28-43 days past a 1-day SLA" finding.
  * `reports/portfolio_history.parquet` - the ONLY source of dated portfolio
    weights, and therefore the basis of every capital-weighted figure - was
    undeclared in `produces`, absent from every `git add`, absent from the
    upload path, and written by a fail-open function whose return value the
    caller discarded. Four defects on one file.
  * zero sized positions was indistinguishable from a sizing failure, even
    though on 2026-10-27 it was correct: all 228 India recommendations are
    HOLD.

These tests pin each repair. They assert the evidence chain, not strategy.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "aegis-daily.yml"
GATE = ROOT / "scripts" / "ci_artifact_integrity.py"


def _steps():
    doc = yaml.safe_load(WF.read_text(encoding="utf-8"))
    return [s for j in doc["jobs"].values() for s in (j.get("steps") or [])]


def _idx(pat):
    for i, s in enumerate(_steps()):
        if pat in (s.get("run") or ""):
            return i
    return -1


# ── R1 · declaration ─────────────────────────────────────────────────
def test_portfolio_history_is_declared_as_produced():
    """Undeclared means _check_produced is blind to it."""
    src = (ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    at = src.find('"name": "portfolio_engine"')
    assert at > 0, "portfolio_engine step disappeared"
    nxt = src.find('"name":', at + 10)
    blk = src[at:nxt if nxt > at else at + 2500]
    assert "reports/portfolio_history.parquet" in blk, (
        "portfolio_history.parquet is no longer declared in produces. It is "
        "the only dated weight history in the system; undeclared, a failure "
        "to write it reports SUCCESS and capital-weighted accounting silently "
        "loses a day.")


# ── R2 · durable persistence ─────────────────────────────────────────
def test_portfolio_history_is_persisted_to_git():
    wf = WF.read_text(encoding="utf-8")
    assert "git add reports/portfolio_history.parquet" in wf, (
        "portfolio_history.parquet lost its persistence. A 30-day CI artifact "
        "cannot hold a multi-month weight series, and capital-weighted return "
        "needs the whole thing - this is authoritative durable state.")


# ── R3 · the silent failure is surfaced ──────────────────────────────
def test_history_append_failure_is_reported():
    src = (ROOT / "india" / "portfolio_engine" / "run.py").read_text(
        encoding="utf-8")
    assert "_row = append_snapshot_row(" in src, (
        "the append return value is being discarded again - append_snapshot_row "
        "is fail-open and returns None on failure, so discarding it makes a "
        "lost history write completely silent")
    assert "portfolio_history append FAILED" in src


# ── R4 · run outputs retained, secrets not ───────────────────────────
def test_run_outputs_are_uploaded_as_a_ci_artifact():
    ups = [s for s in _steps() if "upload-artifact" in str(s.get("uses", ""))]
    assert len(ups) >= 2, (
        "the risk/portfolio upload is gone - before it was added the "
        "workflow's only upload was the Telegram log, so 99 of 138 artifacts "
        "were destroyed with the runner")
    tgt = [u for u in ups
           if "run-outputs" in str(u.get("with", {}).get("name", ""))]
    assert tgt, "no aegis-india-run-outputs artifact step"
    w = tgt[0]["with"]
    paths = str(w.get("path", ""))
    for required in ("reports/sized_positions.json",
                     "reports/portfolio_history.parquet",
                     "reports/context/orchestrator_verdict_india.json"):
        assert required in paths, "%s not retained" % required
    assert w.get("retention-days"), "retention must be explicit"


def test_upload_paths_cannot_sweep_secrets():
    """Explicit paths only · a glob here would publish credentials."""
    ups = [s for s in _steps() if "upload-artifact" in str(s.get("uses", ""))]
    for u in ups:
        for line in str(u.get("with", {}).get("path", "")).splitlines():
            ln = line.strip()
            if not ln:
                continue
            assert not ln.startswith("*"), "bare glob in upload path: %r" % ln
            assert ln not in (".", "./", "/"), "whole-tree upload: %r" % ln
            low = ln.lower()
            for danger in (".env", "secret", "credential", "token",
                           "id_rsa", ".pem", ".key"):
                assert danger not in low, (
                    "upload path may publish sensitive material: %r" % ln)


# ── R5 · ordering ────────────────────────────────────────────────────
def test_integrity_gate_runs_after_the_producers():
    orch = _idx("aegis_daily_v2.py")
    gate = _idx("ci_artifact_integrity.py")
    assert orch >= 0, "orchestrator step missing"
    assert gate >= 0, (
        "the post-production integrity gate is gone. Without it the only "
        "artifact validation is backend_validation at orchestrator step 6, "
        "which grades the leftovers from before the run.")
    assert gate > orch, (
        "the integrity gate runs at step %d, BEFORE the orchestrator at %d - "
        "it would grade pre-run leftovers, which is the defect it exists to "
        "fix" % (gate, orch))


def test_backend_validation_was_not_relocated():
    """It also validates SOURCE data that must precede scoring."""
    src = (ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    import re
    names = [m.group(1) for m in re.finditer(r'"name":\s*"([a-z0-9_]+)"', src)]
    order = {n: i for i, n in enumerate(names)}
    bv, re_ = order.get("backend_validation"), order.get("risk_engine")
    assert bv is not None and re_ is not None
    assert bv < re_, (
        "backend_validation was moved after risk_engine. It validates source "
        "data (price bars, fundamentals, macro) that must be checked BEFORE "
        "scoring - the repair was to ADD post-production verification, not to "
        "relocate the pre-flight.")


# ── R6 · the empty-portfolio contract ────────────────────────────────
@pytest.fixture
def sandbox(tmp_path):
    """A repo-shaped tree the real gate can run against."""
    (tmp_path / "reports" / "context").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(GATE, tmp_path / "scripts" / "ci_artifact_integrity.py")
    return tmp_path


def _write(sb, rel, doc):
    p = sb / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def _run(sb):
    r = subprocess.run([sys.executable,
                        str(sb / "scripts" / "ci_artifact_integrity.py"),
                        "--market", "india", "--asof", "2026-10-27"],
                       capture_output=True, text=True, cwd=str(sb))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _full_set(sb, n_pos, actions):
    for rel in ("reports/sized_positions.json", "reports/risk_report.json",
                "reports/portfolio_state.json"):
        _write(sb, rel, {"asof": "2026-10-27", "n_positions": n_pos})
    _write(sb, "reports/portfolio_v3.json", {"asof": "2026-10-27"})
    _write(sb, "reports/recommendations_v3.json",
           {"asof": "2026-10-27",
            "recommendations": [{"action": a} for a in actions]})
    # parquet stand-in: the gate reports OUTPUT_MISSING if absent, which is
    # correct, so give it one via pandas
    import pandas as pd
    pd.DataFrame([{"asof": "2026-10-27", "market": "india"}]).to_parquet(
        sb / "reports" / "portfolio_history.parquet", index=False)


def test_zero_positions_with_all_hold_is_VALID_EMPTY(sandbox):
    """2026-10-27's real case: 228 HOLD, zero positions, correct."""
    _full_set(sandbox, 0, ["HOLD"] * 228)
    code, out = _run(sandbox)
    assert "VALID_EMPTY" in out
    assert code == 0, (
        "a legitimately empty portfolio failed the gate. All 228 "
        "recommendations are HOLD, so zero positions is correct - failing "
        "here would block delivery on a correct run.\n%s" % out)


def test_zero_positions_WHILE_buys_exist_is_INVALID(sandbox):
    """The case that must never pass as 'valid empty'."""
    _full_set(sandbox, 0, ["BUY"] * 5 + ["HOLD"] * 223)
    code, out = _run(sandbox)
    assert "INVALID_INPUT" in out, (
        "zero positions while actionable BUY recommendations exist is a "
        "sizing failure and must not be excused as VALID_EMPTY\n%s" % out)
    assert code == 1


def test_missing_output_fails_closed(sandbox):
    _full_set(sandbox, 0, ["HOLD"] * 10)
    (sandbox / "reports" / "sized_positions.json").unlink()
    code, out = _run(sandbox)
    assert "OUTPUT_MISSING" in out and code == 1


def test_stale_output_fails_closed(sandbox):
    _full_set(sandbox, 3, ["BUY"] * 3)
    _write(sandbox, "reports/sized_positions.json",
           {"asof": "2026-09-04", "n_positions": 3})
    code, out = _run(sandbox)
    assert "OUTPUT_STALE" in out, (
        "an artifact from 2026-09-04 passed as belonging to a 2026-10-27 "
        "run - exactly the failure that hid the portfolio engine for 54 "
        "days\n%s" % out)
    assert code == 1


def test_malformed_output_is_rejected(sandbox):
    _full_set(sandbox, 2, ["BUY"] * 2)
    (sandbox / "reports" / "sized_positions.json").write_text(
        "{not json", encoding="utf-8")
    code, out = _run(sandbox)
    assert "INVALID_INPUT" in out and code == 1


def test_empty_cannot_be_justified_without_the_recommendation_set(sandbox):
    """No evidence means no VALID_EMPTY · it must not default to passing."""
    _full_set(sandbox, 0, ["HOLD"] * 10)
    (sandbox / "reports" / "recommendations_v3.json").unlink()
    code, out = _run(sandbox)
    assert "INVALID_INPUT" in out and code == 1
