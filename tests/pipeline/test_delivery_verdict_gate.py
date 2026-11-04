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


#: The only conjunct permitted alongside always() on the delivery gate.
PERMITTED_CONJUNCT = "steps.guard.outputs.run"


def gate_condition_ok(cond) -> tuple:
    """Is `cond` an acceptable `if:` for the delivery-verdict gate?

    CEO 2026-11-04. The REQUIREMENT is that an upstream failure must not
    skip the gate, so `always()` has to be present. It is no longer the
    whole condition for India.

    India's workflow guards once per IST day. On 2026-11-04 the 06:00 run
    did the day's work and the 06:49, 07:18 and 07:46 backups correctly
    short-circuited - steps #5 to #31 all skipped - and a bare
    `always()` made this gate run anyway and fail for want of a state
    file those skipped steps never wrote. Three consecutive RED Daily
    runs on a pipeline that had not failed. Fixed in 14ebede10 by adding
    the day-guard conjunct.

    So the check is semantic, not a string comparison, and it is still
    strict: `always()` must be there, and the ONLY extra conjunct
    allowed is the day guard. Anything else - an event filter, another
    step's outcome, a branch condition - is rejected, because each would
    let the gate be skipped on a run that really did execute.
    """
    c = str(cond or "")
    if "always()" not in c:
        return False, "always() absent · an upstream failure would skip the gate"
    extra = [x.strip() for x in c.split("&&") if "always()" not in x]
    bad = [x for x in extra if PERMITTED_CONJUNCT not in x]
    if bad:
        return False, "condition beyond always() and the day guard: %r" % bad
    return True, ""


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
    ok, why = gate_condition_ok(last.get("if"))
    assert ok, "the gate must run even when an earlier step failed · %s" % why


@pytest.mark.parametrize("market", ["usa", "india"])
def test_gate_runs_after_every_commit_step(market):
    """Failing before the commits would lose the very evidence it reports."""
    steps = _steps(market)
    gate = len(steps) - 1
    commits = [i for i, s in enumerate(steps)
               if "git commit" in _effective(s.get("run", ""))]
    assert commits, "no commit step found in %s" % market
    assert max(commits) < gate


# ── Negative cases for the gate condition · CEO 2026-11-04 §4 ──────
# The semantic check replaced an exact string comparison, so it must be
# shown to REJECT as well as accept. Each of these would let the gate be
# skipped on a run that really did execute.
@pytest.mark.parametrize("cond,reason", [
    ("success()",                        "always() absent"),
    ("failure()",                        "always() absent"),
    ("",                                 "empty condition"),
    (None,                               "no condition at all"),
    ("steps.guard.outputs.run == 'true'", "guard without always()"),
    ("always() && github.event_name == 'push'",
     "an event filter would skip scheduled runs"),
    ("always() && steps.send.outcome == 'success'",
     "another step's outcome would skip the gate exactly when it matters"),
    ("always() && github.ref == 'refs/heads/main'",
     "a branch filter would skip the gate on other refs"),
    ("always() && !cancelled()",         "an unrelated conjunct"),
    ("always() && steps.guard.outputs.run == 'true' && success()",
     "a third conjunct beyond the day guard"),
])
def test_an_unacceptable_gate_condition_is_rejected(cond, reason):
    ok, why = gate_condition_ok(cond)
    assert not ok, "accepted %r (%s) · %s" % (cond, reason, why)
    assert why


@pytest.mark.parametrize("cond", [
    "always()",
    "always() && steps.guard.outputs.run == 'true'",
    "steps.guard.outputs.run == 'true' && always()",
    "  always()  &&  steps.guard.outputs.run == 'true'  ",
])
def test_an_acceptable_gate_condition_is_accepted(cond):
    ok, why = gate_condition_ok(cond)
    assert ok, "rejected %r · %s" % (cond, why)


def test_the_permitted_conjunct_is_the_day_guard_and_nothing_else():
    """Pinned · widening this set is a deliberate act, not a drift."""
    assert PERMITTED_CONJUNCT == "steps.guard.outputs.run"
