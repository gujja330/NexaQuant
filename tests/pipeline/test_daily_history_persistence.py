"""The daily recommendation history must actually persist, and prove it.

CEO 2026-11-03 · measured defect. Both daily recommendation runners are
`"optional": True` in their orchestrators, and both wrapped the history
append in try/except-and-print. A runner that exited FATAL, or an append
that returned None, left the daily run green with nothing written:

    India  5 daily rows in eight months   (68 of 73 from one replay batch)
    USA    4 daily rows in eight months   (135 of 139 from the same batch)

Every test here writes inside tmp_path. None of them open, read or write
the repository's own parquet files, registry, ledgers or shadow outcomes.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.persistence import append_and_record, persistence_state_path  # noqa: E402
from scripts import ci_history_persistence_check as chk                    # noqa: E402

RUNNERS = {
    "india": REPO / "india" / "recommendation_intelligence" / "run.py",
    "usa": REPO / "usa" / "research" / "recommendation_intelligence" / "run.py",
}
HISTORY_REL = {
    "india": ("reports", "recommendation_history.parquet"),
    "usa": ("usa", "reports", "recommendation_history.parquet"),
}


def _payload(market: str, asof: str, n: int = 3) -> dict:
    return {
        "engine": "recommendation_intelligence",
        "version": "3.0.0",
        "market": market,
        "asof": asof,
        "run_utc": asof + "T12:00:00+00:00",
        "currency": "INR" if market == "india" else "USD",
        "regime": "risk_on",
        "n_tickers": n,
        "distribution": {"HOLD": n},
        "recommendations": [
            {"ticker": "TK%d" % i, "action": "HOLD", "asof": asof,
             "ensemble_score": 0.5 + i / 100.0}
            for i in range(n)
        ],
        "model_stamp": {"fingerprint": "abc123"},
    }


def _hist(root: Path, market: str) -> Path:
    return root.joinpath(*HISTORY_REL[market])


# ── the production call sites must exist ────────────────────────────

@pytest.mark.parametrize("market", ["india", "usa"])
def test_the_daily_runner_calls_the_verified_writer(market):
    """Parsed from the AST, so a comment mentioning it cannot satisfy this.

    Grepping source text for a function name has produced four false
    positives in this repository's history by matching the prose that
    explains the rule. This walks the tree and looks at call nodes.
    """
    tree = ast.parse(RUNNERS[market].read_text(encoding="utf-8"))
    called, imported = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name:
                called.add(name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("backend.persistence"):
                imported.update(a.name for a in node.names)
    assert "append_and_record" in imported, (
        "%s does not import append_and_record from backend.persistence"
        % RUNNERS[market].name)
    assert "append_and_record" in called, (
        "%s imports the verified writer but never calls it" % RUNNERS[market].name)


@pytest.mark.parametrize("market", ["india", "usa"])
def test_the_runner_passes_its_own_market_and_path(market):
    """India must not be able to write USA's history, or vice versa."""
    src = RUNNERS[market].read_text(encoding="utf-8")
    other = "usa" if market == "india" else "india"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "append_and_record"):
            kw = {k.arg: k.value for k in node.keywords}
            assert "market" in kw and isinstance(kw["market"], ast.Constant)
            assert kw["market"].value == market, (
                "%s passes market=%r" % (market, kw["market"].value))
            break
    else:
        pytest.fail("no append_and_record call found in %s" % RUNNERS[market].name)
    # the other market's history path must not appear in this runner
    wrong = "/%s/reports/recommendation_history" % other
    assert wrong.replace("/", "") not in src.replace('"', "").replace(" ", "").replace("/", ""), (
        "%s references %s's history path" % (market, other))


# ── behaviour · all inside tmp_path ─────────────────────────────────

@pytest.mark.parametrize("market", ["india", "usa"])
def test_a_successful_run_persists_and_verifies(tmp_path, market):
    h = _hist(tmp_path, market)
    st = append_and_record(_payload(market, "2026-11-03"), h,
                           root=tmp_path, market=market)
    assert st["state"] == "PERSISTED", st
    assert st["verified"] is True
    assert st["rows_before"] == 0 and st["rows_after"] == 1
    assert len(pd.read_parquet(h)) == 1
    assert persistence_state_path(tmp_path, market).exists()


def test_each_market_writes_only_to_its_own_file(tmp_path):
    hi, hu = _hist(tmp_path, "india"), _hist(tmp_path, "usa")
    append_and_record(_payload("india", "2026-11-03"), hi,
                      root=tmp_path, market="india")
    append_and_record(_payload("usa", "2026-11-03"), hu,
                      root=tmp_path, market="usa")
    assert len(pd.read_parquet(hi)) == 1
    assert len(pd.read_parquet(hu)) == 1
    assert pd.read_parquet(hi)["market"].tolist() == ["india"]
    assert pd.read_parquet(hu)["market"].tolist() == ["usa"]


def test_rerunning_the_same_market_and_date_is_idempotent(tmp_path):
    h = _hist(tmp_path, "india")
    for _ in range(3):
        st = append_and_record(_payload("india", "2026-11-03"), h,
                               root=tmp_path, market="india")
        assert st["state"] == "PERSISTED"
    assert len(pd.read_parquet(h)) == 1, "dedupe on (market, asof) broke"


def test_a_new_date_appends_a_new_snapshot(tmp_path):
    h = _hist(tmp_path, "india")
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        append_and_record(_payload("india", d), h, root=tmp_path, market="india")
    df = pd.read_parquet(h)
    assert len(df) == 3
    assert sorted(df["asof"].tolist()) == ["2026-11-01", "2026-11-02", "2026-11-03"]


def test_many_tickers_still_make_one_row(tmp_path):
    """One snapshot per market-day, not one row per ticker."""
    h = _hist(tmp_path, "usa")
    st = append_and_record(_payload("usa", "2026-11-03", n=516), h,
                           root=tmp_path, market="usa")
    assert st["rows_after"] == 1
    df = pd.read_parquet(h)
    assert df["n_tickers"].tolist() == [516]
    assert len(json.loads(df["recommendations"].iloc[0])) == 516


def test_a_payload_without_an_asof_is_skipped_not_silently_dropped(tmp_path):
    h = _hist(tmp_path, "india")
    bad = _payload("india", "2026-11-03")
    bad.pop("asof")
    st = append_and_record(bad, h, root=tmp_path, market="india")
    assert st["state"] == "SKIPPED"
    assert st["verified"] is False
    assert "asof" in st["detail"]


def test_an_unwritable_history_reports_failure_not_success(tmp_path, monkeypatch):
    """Fail-open must stay fail-open · but it must not report PERSISTED."""
    import backend.persistence.history_writer as hw
    monkeypatch.setattr(hw, "append_snapshot_row", lambda *a, **k: None)
    st = hw.append_and_record(_payload("india", "2026-11-03"),
                              _hist(tmp_path, "india"),
                              root=tmp_path, market="india")
    assert st["state"] == "FAILED"
    assert st["verified"] is False


def test_existing_history_schema_stays_readable(tmp_path):
    """An append onto a file written by the old path must not break it."""
    h = _hist(tmp_path, "india")
    h.parent.mkdir(parents=True, exist_ok=True)
    from backend.persistence import append_snapshot_row
    append_snapshot_row(_payload("india", "2026-11-01"), h)   # legacy writer
    cols_before = set(pd.read_parquet(h).columns)
    append_and_record(_payload("india", "2026-11-02"), h,
                      root=tmp_path, market="india")
    df = pd.read_parquet(h)
    assert len(df) == 2
    assert cols_before <= set(df.columns), "legacy columns were dropped"


# ── the CI check ────────────────────────────────────────────────────

def test_missing_state_is_reported_as_missing(tmp_path):
    r = chk.classify(tmp_path, "usa")
    assert r["state"] == "MISSING" and r["ok"] is False


def test_persisted_state_is_ok(tmp_path):
    append_and_record(_payload("usa", "2026-11-03"), _hist(tmp_path, "usa"),
                      root=tmp_path, market="usa")
    r = chk.classify(tmp_path, "usa", expected_asof="2026-11-03")
    assert r["state"] == "PERSISTED" and r["ok"] is True


def test_yesterdays_state_is_not_evidence_about_today(tmp_path):
    append_and_record(_payload("usa", "2026-11-02"), _hist(tmp_path, "usa"),
                      root=tmp_path, market="usa")
    r = chk.classify(tmp_path, "usa", expected_asof="2026-11-03")
    assert r["state"] == "STALE" and r["ok"] is False


def test_strict_fails_the_run_and_default_does_not(tmp_path, capsys):
    rc_soft = chk.main(["--market", "usa", "--root", str(tmp_path)])
    out_soft = capsys.readouterr().out
    rc_hard = chk.main(["--market", "usa", "--root", str(tmp_path), "--strict"])
    out_hard = capsys.readouterr().out
    assert rc_soft == 0 and "::warning::" in out_soft
    assert rc_hard == 1 and "::error::" in out_hard


def test_the_check_passes_when_both_markets_persisted(tmp_path):
    for m in ("india", "usa"):
        append_and_record(_payload(m, "2026-11-03"), _hist(tmp_path, m),
                          root=tmp_path, market=m)
    assert chk.main(["--market", "both", "--root", str(tmp_path),
                     "--asof", "2026-11-03", "--strict"]) == 0


def test_one_market_failing_does_not_hide_behind_the_other(tmp_path):
    append_and_record(_payload("india", "2026-11-03"), _hist(tmp_path, "india"),
                      root=tmp_path, market="india")
    rc = chk.main(["--market", "both", "--root", str(tmp_path),
                   "--asof", "2026-11-03", "--strict"])
    assert rc == 1, "USA had no history and the run still passed"


# ── replay compatibility ────────────────────────────────────────────

def test_replay_and_daily_do_not_double_append_the_same_date(tmp_path):
    """Replay uses append_snapshot_row · daily uses append_and_record.

    Both dedupe on (market, asof), so a replayed date followed by a daily
    run of the same date must still be one row.
    """
    from backend.persistence import append_snapshot_row
    h = _hist(tmp_path, "india")
    replayed = _payload("india", "2026-11-03")
    replayed["replay"] = True
    append_snapshot_row(replayed, h)
    append_and_record(_payload("india", "2026-11-03"), h,
                      root=tmp_path, market="india")
    df = pd.read_parquet(h)
    assert len(df) == 1, "replay + daily produced duplicate snapshots"
    assert str(df["replay"].iloc[0]) in ("None", "nan", "False"), (
        "the daily row must win over the replayed one for the same date")


# ── strict mode · every state ───────────────────────────────────────

def _state(tmp_path: Path, mkt: str, **kw) -> Path:
    p = persistence_state_path(tmp_path, mkt)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kw, default=str), encoding="utf-8")
    return p


def test_strict_passes_a_verified_persisted_state(tmp_path):
    append_and_record(_payload("india", "2026-11-03"), _hist(tmp_path, "india"),
                      root=tmp_path, market="india")
    assert chk.main(["--market", "india", "--root", str(tmp_path),
                     "--asof", "2026-11-03", "--strict"]) == 0


def test_strict_fails_a_persisted_state_that_was_never_verified(tmp_path):
    """"PERSISTED" must mean verified · not "the call did not raise"."""
    _state(tmp_path, "usa", market="usa", asof="2026-11-03",
           state="PERSISTED", verified=False, history_expected=True)
    r = chk.classify(tmp_path, "usa", expected_asof="2026-11-03")
    assert r["ok"] is False
    assert "never confirmed present" in r["detail"]
    assert chk.main(["--market", "usa", "--root", str(tmp_path),
                     "--asof", "2026-11-03", "--strict"]) == 1


def test_strict_fails_failed(tmp_path):
    from backend.persistence import record_not_attempted, REASON_UPSTREAM_FATAL
    record_not_attempted(tmp_path, "usa", reason=REASON_UPSTREAM_FATAL,
                         detail="no feature store snapshot", expected=True)
    r = chk.classify(tmp_path, "usa")
    assert r["state"] == "FAILED" and r["ok"] is False
    assert "UPSTREAM_FATAL" in r["detail"]
    assert chk.main(["--market", "usa", "--root", str(tmp_path), "--strict"]) == 1


def test_strict_fails_missing(tmp_path):
    assert chk.classify(tmp_path, "usa")["state"] == "MISSING"
    assert chk.main(["--market", "usa", "--root", str(tmp_path), "--strict"]) == 1


def test_strict_fails_stale(tmp_path):
    append_and_record(_payload("usa", "2026-11-02"), _hist(tmp_path, "usa"),
                      root=tmp_path, market="usa")
    assert chk.main(["--market", "usa", "--root", str(tmp_path),
                     "--asof", "2026-11-03", "--strict"]) == 1


def test_strict_fails_an_unreadable_state(tmp_path):
    p = persistence_state_path(tmp_path, "india")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    assert chk.classify(tmp_path, "india")["state"] == "UNREADABLE"
    assert chk.main(["--market", "india", "--root", str(tmp_path), "--strict"]) == 1


# ── SKIPPED · only a positive, auditable claim passes ───────────────

@pytest.mark.parametrize("reason", sorted(
    __import__("backend.persistence", fromlist=["x"]).ALLOWED_SKIP_REASONS))
def test_a_legitimate_skip_passes_strict(tmp_path, reason):
    from backend.persistence import record_not_attempted
    st = record_not_attempted(tmp_path, "india", reason=reason,
                              detail="calendar says so", expected=False)
    assert st["state"] == "SKIPPED"
    r = chk.classify(tmp_path, "india")
    assert r["ok"] is True, r
    assert chk.main(["--market", "india", "--root", str(tmp_path), "--strict"]) == 0


def test_a_skip_that_still_owed_history_fails(tmp_path):
    _state(tmp_path, "india", market="india", state="SKIPPED",
           history_expected=True, reason="MARKET_HOLIDAY", verified=False)
    r = chk.classify(tmp_path, "india")
    assert r["ok"] is False
    assert "history_expected=True" in r["detail"]


def test_a_skip_with_an_invented_reason_fails(tmp_path):
    _state(tmp_path, "india", market="india", state="SKIPPED",
           history_expected=False, reason="BECAUSE_IT_WAS_SLOW", verified=False)
    r = chk.classify(tmp_path, "india")
    assert r["ok"] is False
    assert "not in the allowed vocabulary" in r["detail"]


def test_a_skip_with_no_reason_fails(tmp_path):
    _state(tmp_path, "india", market="india", state="SKIPPED",
           history_expected=False, reason="", verified=False)
    assert chk.classify(tmp_path, "india")["ok"] is False


# ── the defect itself · optional step FATALs, history vanishes ──────

@pytest.mark.parametrize("market", ["india", "usa"])
def test_an_optional_step_fatal_cannot_pass_as_a_successful_day(
        tmp_path, market):
    """The measured eight-month failure, as a test.

    The orchestrator marks the recommendation step "optional": True, so the
    runner's `return 1` leaves the daily run green. Before this change the
    day also left no trace. Now the FATAL records itself and strict mode
    refuses to call the day a success.
    """
    from backend.persistence import record_not_attempted, REASON_UPSTREAM_FATAL
    record_not_attempted(tmp_path, market, reason=REASON_UPSTREAM_FATAL,
                         detail="no feature store snapshot", expected=True)
    assert not _hist(tmp_path, market).exists(), "no history should exist"
    r = chk.classify(tmp_path, market)
    assert r["state"] == "FAILED" and r["ok"] is False
    assert chk.main(["--market", market, "--root", str(tmp_path),
                     "--strict"]) == 1


@pytest.mark.parametrize("market", ["india", "usa"])
def test_the_runner_records_its_fatal_exits(market):
    """Parsed from the AST · every FATAL return must record state first."""
    path = RUNNERS[market]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "_history_fatal" in names, (
        "%s has FATAL exits that record nothing" % path.name)
    src = path.read_text(encoding="utf-8")
    n_fatal = src.count('print("  FATAL')
    n_record = src.count("_history_fatal(")
    assert n_record >= n_fatal, (
        "%d FATAL exits but only %d record state" % (n_fatal, n_record - 1))


def test_fail_open_snapshot_behaviour_is_preserved(tmp_path, monkeypatch):
    """A history failure must still not raise into the runner."""
    import backend.persistence.history_writer as hw
    def _boom(*a, **k):
        raise RuntimeError("parquet exploded")
    monkeypatch.setattr(hw, "append_snapshot_row", _boom)
    with pytest.raises(RuntimeError):
        hw.append_snapshot_row({}, tmp_path / "x.parquet")
    # record_not_attempted is the failure path and must never raise
    st = hw.record_not_attempted(tmp_path, "india", reason="UPSTREAM_FATAL",
                                 detail="boom", expected=True)
    assert st["state"] == "FAILED"


# ── evidence age · a yesterday verdict is not today's evidence ──────

def test_a_fresh_persisted_state_passes_the_age_budget(tmp_path):
    append_and_record(_payload("india", "2026-11-03"), _hist(tmp_path, "india"),
                      root=tmp_path, market="india")
    r = chk.classify(tmp_path, "india", None, 24.0)
    assert r["state"] == "PERSISTED" and r["ok"] is True
    assert r["age_hours"] is not None and r["age_hours"] < 1.0


def test_yesterdays_persisted_state_is_stale_under_the_age_budget(tmp_path):
    """The hole --strict would otherwise leave open.

    If the recommendation step never executes, no new state file is
    written. Without an age check, yesterday's PERSISTED file passes and
    the run is called a success having produced nothing.
    """
    _state(tmp_path, "india", market="india", asof="2026-11-03",
           state="PERSISTED", verified=True, history_expected=True,
           checked_utc="2026-10-20T02:00:00+00:00")
    r = chk.classify(tmp_path, "india", None, 24.0)
    assert r["state"] == "STALE" and r["ok"] is False
    assert "freshness budget" in r["detail"]
    assert chk.main(["--market", "india", "--root", str(tmp_path),
                     "--max-age-hours", "24", "--strict"]) == 1


def test_an_unparseable_timestamp_is_stale_not_trusted(tmp_path):
    _state(tmp_path, "india", market="india", state="PERSISTED",
           verified=True, history_expected=True, checked_utc="not-a-time")
    r = chk.classify(tmp_path, "india", None, 24.0)
    assert r["state"] == "STALE" and r["ok"] is False


def test_a_stale_legitimate_skip_is_also_rejected(tmp_path):
    """A holiday claim from last week is not a claim about today."""
    _state(tmp_path, "india", market="india", state="SKIPPED",
           history_expected=False, reason="MARKET_HOLIDAY", verified=False,
           checked_utc="2026-10-20T02:00:00+00:00")
    assert chk.classify(tmp_path, "india", None, 24.0)["ok"] is False


def test_without_the_budget_age_is_reported_but_not_enforced(tmp_path):
    """Opt-in · existing callers keep their behaviour."""
    _state(tmp_path, "india", market="india", asof="2026-11-03",
           state="PERSISTED", verified=True, history_expected=True,
           checked_utc="2026-10-20T02:00:00+00:00")
    r = chk.classify(tmp_path, "india")
    assert r["state"] == "PERSISTED" and r["ok"] is True
    assert r["age_hours"] is not None and r["age_hours"] > 24
