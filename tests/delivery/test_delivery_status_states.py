"""The six delivery states, each proven from evidence built in tmp_path.

CEO 2026-11-03 · "A green GitHub Actions run is not proof of a delivered
workbook." Each test here constructs the exact evidence for one state -
its own git repository, its own workbook, its own validator verdict and
its own delivery ledger - and asserts the classifier reaches that state
and no other. Nothing reads the repository's real workbooks, ledgers or
validator output.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import ci_delivery_status as ds  # noqa: E402

ASOF = "2026-11-03"


def _git(root: Path, *args):
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _workbook(root: Path, market: str, *, asof: str = ASOF, rows: int = 3,
              sheets=("CURRENT", "EXIT HISTORY"), banner_market=None) -> Path:
    from openpyxl import Workbook
    p = ds.workbook_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    name = banner_market or ("India NSE" if market == "india" else "USA S&P 500")
    for s in sheets:
        ws = wb.create_sheet(s)
        ws.cell(1, 1).value = "AEGIS DAILY · %s · %s" % (name, asof)
        ws.cell(4, 1).value = "#"
        ws.cell(4, 2).value = "Ticker"
        for i in range(rows):
            ws.cell(5 + i, 1).value = i + 1
            ws.cell(5 + i, 2).value = "TK%d" % i
    wb.save(p)
    wb.close()
    return p


def _commit_workbook(root: Path, market: str) -> None:
    rel = ds.workbook_path(root, market).relative_to(root).as_posix()
    _git(root, "add", "--", rel)
    _git(root, "commit", "-q", "-m", "wb")


def _validator(root: Path, market: str, *, block_fail=(), block_skip=()) -> None:
    p = root / "reports" / "context" / ("xlsx_validation_%s.json" % market)
    p.parent.mkdir(parents=True, exist_ok=True)
    inv = [{"code": c, "severity": "BLOCK", "status": "FAIL"} for c in block_fail]
    inv += [{"code": c, "severity": "BLOCK", "status": "SKIP"} for c in block_skip]
    inv += [{"code": "I1", "severity": "BLOCK", "status": "PASS"}]
    p.write_text(json.dumps({"verdict": "FAIL" if block_fail else "PASS",
                             "invariants": inv}), encoding="utf-8")


def _ledger(root: Path, entries: list, on: str = ASOF) -> None:
    p = ds.ledger_path(root, on)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n",
                 encoding="utf-8")


def _good(tmp_path: Path, market: str = "usa") -> Path:
    """A repo where everything up to delivery is correct."""
    root = _repo(tmp_path)
    _workbook(root, market)
    _commit_workbook(root, market)
    _validator(root, market)
    return root


# ── XLSX_GENERATION_FAILURE ─────────────────────────────────────────

def test_missing_workbook(tmp_path):
    st = ds.classify(_repo(tmp_path), "usa", ASOF)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE
    assert "does not exist" in st["reason"]


def test_zero_byte_workbook(tmp_path):
    root = _repo(tmp_path)
    p = ds.workbook_path(root, "usa")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE
    assert "zero bytes" in st["reason"]


def test_a_workbook_naming_the_wrong_market(tmp_path):
    """USA's path holding a workbook whose banner says India."""
    root = _repo(tmp_path)
    _workbook(root, "usa", banner_market="India NSE")
    _commit_workbook(root, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE
    assert "market identity" in st["reason"]


def test_a_workbook_dated_another_day(tmp_path):
    root = _repo(tmp_path)
    _workbook(root, "usa", asof="2026-10-28")
    _commit_workbook(root, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE
    assert "asof" in st["reason"]


def test_a_workbook_with_headers_and_no_data(tmp_path):
    root = _repo(tmp_path)
    _workbook(root, "usa", rows=0)
    _commit_workbook(root, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE
    assert "no data rows" in st["reason"]


def test_a_missing_required_sheet(tmp_path):
    root = _repo(tmp_path)
    _workbook(root, "usa", sheets=("CURRENT",))
    _commit_workbook(root, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE
    # The reason names the missing LOGICAL sheet and what was actually in
    # the workbook. It used to name the legacy literal "Exit History (90d)",
    # which the sheet-lookup scanners correctly flagged as a private copy
    # of a sheet name; the logical id cannot drift the same way.
    assert ds.LOGICAL_EXIT_HISTORY in st["reason"]
    assert "CURRENT" in st["reason"], "and says what it did find"


def test_sheet_aliases_are_honoured(tmp_path):
    """CURRENT / EXIT HISTORY must resolve · the locked two-sheet names.

    The first version of this classifier required the literal name
    "Portfolio" and failed two perfectly good workbooks.
    """
    root = _good(tmp_path, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] != ds.XLSX_GENERATION_FAILURE, st["reason"]
    assert st["workbook"]["sheets"] == ["CURRENT", "EXIT HISTORY"]


# ── ARTIFACT_PERSISTENCE_FAILURE ────────────────────────────────────

def test_an_uncommitted_workbook_is_not_persisted(tmp_path):
    root = _repo(tmp_path)
    _workbook(root, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.ARTIFACT_PERSISTENCE_FAILURE
    assert "not tracked" in st["reason"]


def test_a_workbook_changed_after_its_commit_is_not_persisted(tmp_path):
    """Produce-then-discard · the repo holds yesterday's copy."""
    root = _repo(tmp_path)
    _workbook(root, "usa", rows=3)
    _commit_workbook(root, "usa")
    _workbook(root, "usa", rows=9)          # regenerate, do not commit
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.ARTIFACT_PERSISTENCE_FAILURE
    assert "differs from the one on disk" in st["reason"]


# ── DELIVERY_BLOCKED ────────────────────────────────────────────────

def test_a_block_invariant_blocks_delivery(tmp_path):
    root = _good(tmp_path, "usa")
    _validator(root, "usa", block_fail=("I28", "I6"))
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_BLOCKED
    assert "I28" in st["reason"] and "I6" in st["reason"]


def test_blocked_outranks_a_successful_looking_ledger(tmp_path):
    """A send recorded as ok cannot override a refusing gate."""
    root = _good(tmp_path, "usa")
    _validator(root, "usa", block_fail=("I28",))
    _ledger(root, [{"ok": True, "file": "reports/telegram/aegis_history_usa.xlsx"}])
    assert ds.classify(root, "usa", ASOF)["state"] == ds.DELIVERY_BLOCKED


# ── DELIVERY_FAILURE ────────────────────────────────────────────────

def test_no_ledger_at_all_is_a_delivery_failure(tmp_path):
    """The measured condition · the ledger is untracked, so CI loses it."""
    st = ds.classify(_good(tmp_path, "usa"), "usa", ASOF)
    assert st["state"] == ds.DELIVERY_FAILURE
    assert "left no record" in st["reason"]


def test_a_send_that_reported_not_ok(tmp_path):
    root = _good(tmp_path, "usa")
    _ledger(root, [{"ok": False, "file": "reports/telegram/aegis_history_usa.xlsx",
                    "error": "429 Too Many Requests"}])
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_FAILURE
    assert "ok=False" in st["reason"]


def test_another_markets_record_does_not_count_as_this_markets_delivery(tmp_path):
    root = _good(tmp_path, "usa")
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_india.xlsx"}])
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_FAILURE
    assert "none for aegis_history_usa.xlsx" in st["reason"]


def test_the_unified_workbook_does_not_count_either(tmp_path):
    """Telegram policy is per-market · aegis_history.xlsx is not USA's."""
    root = _good(tmp_path, "usa")
    _ledger(root, [{"ok": True, "kind": "unified_xlsx",
                    "file": "reports/telegram/aegis_history.xlsx"}])
    assert ds.classify(root, "usa", ASOF)["state"] == ds.DELIVERY_FAILURE


# ── DELIVERY_SUCCESS ────────────────────────────────────────────────

def test_a_verified_delivery(tmp_path):
    root = _good(tmp_path, "usa")
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_usa.xlsx"}])
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_SUCCESS
    assert st["sha256"] and len(st["sha256"]) == 64
    assert st["workbook"]["data_rows"] == 3


def test_the_last_record_for_the_market_decides(tmp_path):
    root = _good(tmp_path, "usa")
    _ledger(root, [
        {"ok": False, "file": "reports/telegram/aegis_history_usa.xlsx"},
        {"ok": True, "file": "reports/telegram/aegis_history_usa.xlsx"},
    ])
    assert ds.classify(root, "usa", ASOF)["state"] == ds.DELIVERY_SUCCESS


# ── PIPELINE_SUCCESS ────────────────────────────────────────────────

def test_pipeline_success_when_no_delivery_was_expected(tmp_path):
    root = _good(tmp_path, "usa")
    st = ds.classify(root, "usa", ASOF, expect_delivery=False)
    assert st["state"] == ds.PIPELINE_SUCCESS
    assert "not expected" in st["reason"]


def test_no_delivery_expected_still_fails_a_bad_workbook(tmp_path):
    """Not expecting delivery is not a licence to skip the workbook checks."""
    root = _repo(tmp_path)
    _workbook(root, "usa", rows=0)
    _commit_workbook(root, "usa")
    st = ds.classify(root, "usa", ASOF, expect_delivery=False)
    assert st["state"] == ds.XLSX_GENERATION_FAILURE


# ── inert gates and exit codes ──────────────────────────────────────

def test_inert_block_invariants_are_surfaced_not_swallowed(tmp_path):
    root = _good(tmp_path, "usa")
    _validator(root, "usa", block_skip=("I8", "I24", "I25", "I26", "I29"))
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_usa.xlsx"}])
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_SUCCESS
    assert st["inert_block_invariants"] == ["I8", "I24", "I25", "I26", "I29"]


def test_main_exits_nonzero_and_annotates_on_failure(tmp_path, capsys):
    rc = ds.main(["--market", "usa", "--asof", ASOF, "--root", str(_repo(tmp_path))])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out and ds.XLSX_GENERATION_FAILURE in out


def test_main_exits_zero_on_delivery_success_and_writes_status(tmp_path):
    root = _good(tmp_path, "usa")
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_usa.xlsx"}])
    assert ds.main(["--market", "usa", "--asof", ASOF, "--root", str(root)]) == 0
    rec = json.loads(ds.status_path(root, "usa").read_text(encoding="utf-8"))
    assert rec["state"] == ds.DELIVERY_SUCCESS
    assert rec["sha256"]


def test_one_market_failing_does_not_hide_behind_the_other(tmp_path):
    root = _good(tmp_path, "usa")
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_usa.xlsx"}])
    # india has no workbook at all
    assert ds.main(["--market", "both", "--asof", ASOF, "--root", str(root)]) == 1


@pytest.mark.parametrize("state", [
    ds.XLSX_GENERATION_FAILURE, ds.ARTIFACT_PERSISTENCE_FAILURE,
    ds.DELIVERY_BLOCKED, ds.DELIVERY_FAILURE,
])
def test_every_failure_state_is_non_passing(state):
    assert state not in ds.PASSING


def test_only_two_states_pass():
    assert set(ds.PASSING) == {ds.DELIVERY_SUCCESS, ds.PIPELINE_SUCCESS}


# ── "survives runner termination" · the remote half ─────────────────

def _remote(tmp_path: Path, name: str = "rem") -> Path:
    """A bare repo wired as origin, so origin/main is a real ref."""
    bare = tmp_path.parent / (tmp_path.name + "_" + name + ".git")
    subprocess.run(["git", "init", "--bare", "-q", str(bare)],
                   capture_output=True)
    return bare


def test_a_pushed_artifact_is_persisted(tmp_path):
    root = _repo(tmp_path)
    _workbook(root, "usa")
    _commit_workbook(root, "usa")
    _validator(root, "usa")
    bare = _remote(tmp_path)
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "branch", "-M", "main")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "fetch", "-q", "origin")
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_usa.xlsx"}])
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_SUCCESS, st["reason"]
    assert st["persistence"]["pushed_matches"] is True


def test_committed_but_never_pushed_is_a_persistence_failure(tmp_path):
    """The runner holds it · origin does not · it dies with the runner."""
    root = _repo(tmp_path)
    _workbook(root, "usa", rows=3)
    _commit_workbook(root, "usa")
    bare = _remote(tmp_path, "rem2")
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "branch", "-M", "main")
    _git(root, "push", "-q", "origin", "main")
    # a later run regenerates and commits, but the push fails
    _workbook(root, "usa", rows=7)
    _commit_workbook(root, "usa")
    _git(root, "fetch", "-q", "origin")
    _validator(root, "usa")
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.ARTIFACT_PERSISTENCE_FAILURE
    assert "was not pushed" in st["reason"]


def test_a_missing_origin_is_unanswerable_not_a_workbook_defect(tmp_path):
    """A developer tree must not be reported as a bad workbook."""
    root = _repo(tmp_path)
    _workbook(root, "usa")
    _commit_workbook(root, "usa")
    _validator(root, "usa")
    _ledger(root, [{"ok": True,
                    "file": "reports/telegram/aegis_history_usa.xlsx"}])
    st = ds.classify(root, "usa", ASOF)
    assert st["state"] == ds.DELIVERY_SUCCESS
    assert st["persistence"]["pushed_matches"] is None
    assert "cannot confirm" in st["persistence"]["pushed_detail"]
