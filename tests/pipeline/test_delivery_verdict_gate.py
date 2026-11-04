"""A blocked delivery must not read green.

CEO 2026-10-31 · USA certified for weeks while the operator received
nothing. Three things combined:

  1. `xlsx_validator.should_block_send` decides delivery INSIDE the
     sender, after the run contract has already written CERTIFIED.
  2. The send step carries `continue-on-error: true`, so a refusal left
     the workflow fully successful.
  3. `xlsx_validation_<market>.json` - the only file naming the blocking
     rows - was written on every run and staged by no workflow, while
     Actions logs return 403 on this repository.

So the answer to "why did nothing arrive?" was generated every morning
and deleted. These tests pin the gate and its evidence trail.

The workflow assertions strip comment lines before matching. The paths
below appear in the explanatory comments too, so a naive substring test
would pass against its own documentation - the grep-the-prose trap this
repository has already hit three times.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.ci_delivery_verdict import classify, main, verdict_path

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = {"usa": REPO / ".github/workflows/aegis-usa.yml",
             "india": REPO / ".github/workflows/aegis-daily.yml"}


def _inv(code, severity, status, detail="d"):
    return {"code": code, "name": code, "severity": severity,
            "status": status, "detail": detail, "violations": []}


def _write(tmp: Path, market: str, invariants: list, verdict="FAIL") -> Path:
    p = verdict_path(tmp, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"market": market, "asof": "2026-10-31",
                             "verdict": verdict,
                             "invariants": invariants}), encoding="utf-8")
    return p


def _steps(market: str) -> list:
    d = yaml.safe_load(WORKFLOWS[market].read_text(encoding="utf-8"))
    return list(d["jobs"].values())[0]["steps"]


def _effective(text: str) -> str:
    """Drop comment lines · a path named only in a comment is not wired."""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        out.append(line.split(" #")[0] if " #" in line else line)
    return "\n".join(out)


def test_the_comment_stripper_actually_strips():
    """Without this the workflow tests below could pass on prose."""
    assert "secret" not in _effective("  # mentions secret here\n  real: 1")
    assert "real" in _effective("  # mentions secret here\n  real: 1")


# ── classification ──────────────────────────────────────────────────────
def test_block_fail_is_delivery_blocked():
    res = classify({"invariants": [_inv("I28", "BLOCK", "FAIL")]})
    assert res["delivery_blocked"] is True
    assert [r["code"] for r in res["blocked"]] == ["I28"]


def test_block_skip_is_inert_not_blocking():
    """A BLOCK invariant that did not evaluate is not a passing check.

    Eleven of them SKIPped on one measured USA run - ten on
    'BadZipFile: Bad magic number', i.e. the validator read a workbook
    that was still being written. Surfaced, not failed: it predates this
    change and failing on it would block delivery outright.
    """
    res = classify({"invariants": [_inv("I28", "BLOCK", "SKIP")]})
    assert res["delivery_blocked"] is False
    assert [r["code"] for r in res["inert"]] == ["I28"]


def test_warn_severity_never_blocks():
    res = classify({"invariants": [_inv("I9", "WARN", "FAIL")]})
    assert res["delivery_blocked"] is False


# ── exit codes ──────────────────────────────────────────────────────────
def test_blocked_verdict_exits_nonzero(tmp_path):
    _write(tmp_path, "usa", [_inv("I28", "BLOCK", "FAIL")])
    assert main(["--market", "usa", "--root", str(tmp_path)]) == 1


def test_clean_verdict_exits_zero(tmp_path):
    _write(tmp_path, "usa", [_inv("I28", "BLOCK", "PASS")], verdict="PASS")
    assert main(["--market", "usa", "--root", str(tmp_path)]) == 0


def test_missing_verdict_file_exits_zero(tmp_path):
    """The sender never reached the validator · its own exit code covers it."""
    assert main(["--market", "usa", "--root", str(tmp_path)]) == 0


def test_inert_only_exits_zero_but_is_reported(tmp_path, capsys):
    _write(tmp_path, "usa", [_inv("I28", "BLOCK", "SKIP")], verdict="WARN")
    assert main(["--market", "usa", "--root", str(tmp_path)]) == 0
    assert "did not evaluate" in capsys.readouterr().out


# ── the evidence trail must be committed ────────────────────────────────
@pytest.mark.parametrize("market", ["usa", "india"])
def test_workflow_stages_the_validator_verdict(market):
    body = "\n".join(_effective(s.get("run", "")) for s in _steps(market))
    assert "xlsx_validation_%s.json" % market in body, (
        "%s never commits the verdict that decides delivery · the reason "
        "nothing arrived would be discarded again" % market)
    assert "health_monitor_%s.json" % market in body, (
        "%s never commits Guard 7's verdict" % market)


@pytest.mark.parametrize("market", ["usa", "india"])
def test_workflow_fails_when_delivery_blocked(market):
    steps = _steps(market)
    last = steps[-1]
    assert "ci_delivery_verdict.py" in _effective(last.get("run", "")), (
        "the delivery-verdict gate is not the final step of %s" % market)
    assert "--market %s" % market in _effective(last.get("run", ""))
    cond = str(last.get("if") or "")
    # CEO 2026-11-04 · the REQUIREMENT is that a failure upstream must not
    # skip the gate, so `always()` must be present. It is no longer the
    # whole condition for India.
    #
    # India's workflow guards once per IST day. On 2026-11-04 the 06:00
    # run did the day's work and the 06:49, 07:18 and 07:46 backups
    # correctly short-circuited - steps #5 to #31 all skipped - and a
    # bare `always()` made this gate run anyway and fail for want of a
    # state file those skipped steps never wrote. Three consecutive RED
    # Daily runs, and the pipeline had not failed at all. Fixed in
    # 14ebede10 by adding the guard conjunct.
    #
    # So this asserts the semantic rather than the literal string: the
    # gate still runs after an upstream failure, and the only permitted
    # additional conjunct is the day guard - a run deliberately skipped
    # is not a failure to report on. Anything else would be a real
    # weakening and still fails here.
    assert "always()" in cond, (
        "the gate must run even when an earlier step failed · if=%r" % cond)
    extra = [c.strip() for c in cond.split("&&") if "always()" not in c]
    assert all("steps.guard.outputs.run" in c for c in extra), (
        "the gate carries a condition beyond always() and the day guard: "
        "%r" % extra)


@pytest.mark.parametrize("market", ["usa", "india"])
def test_gate_runs_after_every_commit_step(market):
    """Failing before the commits would lose the very evidence it reports."""
    steps = _steps(market)
    gate = len(steps) - 1
    commits = [i for i, s in enumerate(steps)
               if "git commit" in _effective(s.get("run", ""))]
    assert commits, "no commit step found in %s" % market
    assert max(commits) < gate
