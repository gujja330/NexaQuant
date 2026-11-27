from datetime import date, datetime, timezone
import json
from pathlib import Path
from subprocess import TimeoutExpired
import subprocess
import sys
from tempfile import TemporaryDirectory

import pytest

from scripts.aegis_shadow.calendar import exchange_calendar
from scripts.aegis_shadow.commit import finish, prepare
from scripts.aegis_shadow.daily import _certify, _checkpoint, _plan, _workbook
from scripts.aegis_shadow.evidence_archive import retain
from scripts.aegis_shadow.execution_accounting import reconcile
from scripts.aegis_shadow.identity import _append_price_history
from scripts.aegis_shadow.learning_observations import summarize
from scripts.aegis_shadow.operations import run_with_timeout_retry, worker_retry
from scripts.aegis_shadow.pipeline import Stage, _execute
from scripts.aegis_shadow.position_history import position_snapshot, read, record
from scripts.aegis_shadow.publication import publish
from scripts.aegis_shadow.stage_cache import reuse_regime, seal_regime
from scripts.aegis_shadow.sandbox import launcher, worker_command
from scripts.aegis_workbook_continuity import discover


ROOT = Path(__file__).resolve().parents[2]


def test_sandbox_command_grants_a_single_workspace_bind(tmp_path):
    work = tmp_path / ".aegis-local/unified/daily/usa/fixture/work"
    work.mkdir(parents=True)
    command = worker_command(tmp_path / "bwrap", work, ["python", "worker.py"])
    assert command[command.index("--ro-bind") + 1:][:2] == ["/", "/"]
    assert command[command.index("--bind") + 1:][:2] == [str(work.resolve())] * 2
    assert command.count("--bind") == 1
    assert command[-3:] == ["--", "python", "worker.py"]
    with pytest.raises(ValueError, match="private unified"):
        worker_command(tmp_path / "bwrap", tmp_path, ["python"])


def test_native_worker_cannot_write_outside_private_workspace():
    try:
        executable = launcher()
    except RuntimeError as error:
        pytest.skip(str(error))
    with TemporaryDirectory(dir=Path.home()) as directory:
        root = Path(directory)
        work = root / ".aegis-local/unified/daily/usa/fixture/work"
        work.mkdir(parents=True)
        protected = root / "legacy.txt"
        protected.write_text("original", encoding="utf-8")
        script = """import ctypes, os, sys
assert open(sys.argv[1], encoding='utf-8').read() == 'original'
libc = ctypes.CDLL(None)
libc.fopen.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
libc.fopen.restype = ctypes.c_void_p
assert libc.fopen(os.fsencode(sys.argv[1]), b'wb') is None
with open('private.txt', 'w', encoding='utf-8') as target:
    target.write('private')
"""
        subprocess.run(worker_command(executable, work, [sys.executable, "-c", script, str(protected)]),
                       check=True, timeout=30)
        assert protected.read_text(encoding="utf-8") == "original"
        assert (work / "private.txt").read_text(encoding="utf-8") == "private"


def test_pending_commit_recovers_after_publication_failure(tmp_path, monkeypatch):
    private = tmp_path / "private"
    work = private / "attempt/work"
    work.mkdir(parents=True)
    state = {"market": "usa", "runner": "new", "workspace": "attempt/work", "asof": "2026-11-26",
             "market_data_asof": "2026-11-25", "workbook_sha256": "verified"}
    prepare(private, work, work.parent, state, {"positions": "hash"})

    def unavailable(*_):
        raise OSError("interrupted publication")

    monkeypatch.setattr("scripts.aegis_shadow.commit.publish", unavailable)
    with pytest.raises(OSError, match="interrupted publication"):
        finish(tmp_path, private, "usa", lambda *_: None)
    assert not (private / "accepted.json").exists()
    observed = []
    monkeypatch.setattr("scripts.aegis_shadow.commit.publish", lambda *args: {"workbook": "verified.xlsx"})
    finish(tmp_path, private, "usa", lambda path, checksums: observed.append((path, checksums)))
    assert observed == [(work.resolve(), {"positions": "hash"})]
    assert json.loads((private / "accepted.json").read_text())["workbook"] == "verified.xlsx"
    assert finish(tmp_path, private, "usa", lambda *_: pytest.fail("replayed completed transaction")) is None


def _write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_reviewed_schedule_handles_dst_early_close_and_year_transition(tmp_path):
    _write(tmp_path, "inputs/usa/exchange_calendar.json", {
        "schema": "aegis.exchange_calendar.v1", "market": "usa", "timezone": "America/New_York",
        "source": "synthetic reviewed fixture", "coverage_start": "2026-12-31", "coverage_end": "2027-03-15",
        "sessions": [{"date": day, "close": close} for day, close in (
            ("2026-12-31", "16:00"), ("2027-01-04", "16:00"), ("2027-03-12", "16:00"), ("2027-03-15", "13:00"))],
    })
    calendar = exchange_calendar("usa", tmp_path)
    before = calendar.completed(datetime(2027, 3, 15, 16, 59, tzinfo=timezone.utc))
    after = calendar.completed(datetime(2027, 3, 15, 17, tzinfo=timezone.utc))
    assert before.isoformat() == "2027-03-12"
    assert after.isoformat() == "2027-03-15"
    assert calendar.missing(date(2026, 12, 31), after) == ["2027-01-04", "2027-03-12"]


@pytest.mark.parametrize("market", ("india", "usa"))
def test_live_plan_preserves_recovery_and_failure_boundaries(market):
    stages = {item.name: item for item in _plan(ROOT, market, "2026-11-26")}
    first_ingestion = "refresh_prices" if market == "india" else "build_universe"
    assert not stages[first_ingestion].requires
    assert "session_checkpoint" in stages["registry"].requires
    assert "history_recovery" in stages["registry"].requires
    names = list(stages)
    assert names.index("history_recovery") > names.index("freshness" if market == "india" else "refresh_market_data")
    assert "position_history" in stages["certify"].requires
    calls = []

    def unavailable(_):
        raise ValueError("fixture provider unavailable")

    stages = (Stage("provider", unavailable), Stage("consumer", lambda _: calls.append("consumer"), ("provider",)),
              Stage("independent", lambda _: calls.append("independent")),
              Stage("certify", lambda _: calls.append("certify"), ("provider", "independent")))
    results = _execute({"market": market}, stages)
    assert calls == ["independent"]
    assert results["consumer"]["blocked_by"] == ["provider"]
    assert results["certify"]["status"] == "BLOCKED"


def test_degraded_history_is_content_addressed_and_preserves_revisions(tmp_path):
    work, storage = tmp_path / "work", tmp_path / "archive"
    storage.mkdir()
    artifact = _write(work, "reports/feature.json", {"data": "original"})
    summary = {"market": "usa", "market_data_asof": "2026-11-25", "asof": "2026-11-26",
               "status": "SHADOW_DEGRADED", "stages": {"features": {"status": "PASS"}}}
    first = retain(storage, work, summary, {"features": {artifact}})
    assert retain(storage, work, summary, {"features": {artifact}}) == first
    manifest = json.loads((storage / first["manifest"]).read_text(encoding="utf-8"))
    checksum = manifest["files"]["reports/feature.json"]["sha256"]
    assert manifest["validation_status"] == "SHADOW_DEGRADED"
    _write(work, "reports/feature.json", {"data": "corrected"})
    assert retain(storage, work, summary, {"features": {artifact}})["manifest"] != first["manifest"]
    assert json.loads((storage / "history/usa/objects" / checksum[:2] / checksum).read_text()) == {"data": "original"}


def test_operational_retry_budget_retries_only_timeouts(tmp_path):
    _write(tmp_path, ".aegis-local/unified/inputs/usa/operations.json", {
        "market": "usa", "research_timeout_attempts": 2, "retry_backoff_seconds": 0,
    })
    seen = []

    def operation(number):
        if number == 1:
            raise TimeoutExpired("fixture", 1)
        return "complete"

    assert run_with_timeout_retry(operation, *worker_retry(tmp_path, "usa"), on_timeout=seen.append) == "complete"
    assert seen == [1]


def test_longitudinal_open_observations_keep_stale_and_changed_entry_basis_out():
    def day(date_value, price, *, entry=100, current=True):
        return {"session": date_value, "positions": {"episode": {
            "entry_date": "2026-11-20", "price_current": current, "entry_price": entry, "observed_price": price,
        }}}

    row = summarize([day("2026-11-23", 90), day("2026-11-24", 120, current=False),
                     day("2026-11-25", 150, entry=110), day("2026-11-26", 105)])["episode"]
    assert row["observations"] == 2
    assert row["entry_reference_conflict"] is True
    assert row["max_observed_return_pct"] == pytest.approx(5)
    assert row["min_observed_return_pct"] == pytest.approx(-10)
    assert row["first_profitable_observation"] == "2026-11-26"


@pytest.mark.parametrize("market,ticker,session,asof", (
    ("india", "INFY", "2026-11-26", "2026-11-26"), ("usa", "BRK.B", "2026-11-25", "2026-11-26"),
))
def test_fixture_session_through_position_history_and_publication(tmp_path, market, ticker, session, asof):
    work = tmp_path / "work"
    output = tmp_path / "attempt"
    output.mkdir()
    reports = "reports" if market == "india" else "usa/reports"
    identity = {"market": market, "asof": asof}
    pid = f"{market}-R2-{ticker}-episode"
    row = dict(position_id=pid, market=market.upper(), ticker=ticker, engine="R2", action="ACTIVE+",
               entry_date="2026-11-20", entry_price=100.0, current_price=110.0, stop=104.0, target=108.0,
               stop_state="INTACT", pnl_pct=10.0, market_data_asof=session, stop_basis="dynamic_risk_v2")
    _write(work, f"reports/context/canonical_lifecycle_{market}.json",
           dict(identity, market_data_asof=session, current=[row], exits=[], input_freshness=[], counts={}))
    _write(work, f"reports/context/dynamic_risk_{market}.json",
           dict(identity, monotonic=True, updates=[{"opportunity_id": pid, "stop_type": "trailing", "original_stop": 94}]))
    _write(work, f"reports/audit/dynamic_exit_decisions_{market}_{asof}.json", dict(identity, decisions=[{
        "opportunity_id": pid, "event": "HOLD", "action": "AUDIT_ONLY", "price_basis_date": session,
        "horizon_days": 10,
    }]))
    _write(work, f"{reports}/backend_validation_summary.json", {"verdict": "PASS", "counts": {"FAIL": 0}})
    _write(work, f"{reports}/portfolio_v3.json", dict(identity, snapshot=dict(
        identity, n_positions=1, positions=[{"ticker": ticker, "weight": 0.5}],
        total_weight=0.5, cash_pct=0.5, cash_reserve_target=0.1)))
    _write(work, "configs/risk_budget.yaml", {"market_defaults": {market: {
        "enable_shorts": False, "per_ticker_cap": 0.6, "per_sector_cap": 0.6,
    }}})
    if market == "usa":
        _write(work, f"{reports}/ops_check.json", {"verdict": "HEALTHY"})
    recommendations = [{"ticker": ticker}]
    _write(work, f"{reports}/recommendations.json", dict(identity, recommendations=recommendations))
    _write(work, f"{reports}/recommendations_history/{market}/{asof}.json",
           {"snapshot_asof": asof, "recommendations": recommendations})
    _write(work, "reports/context/ssot_health.json", {market: {"verdict": "GREEN", "output_asof": asof}})
    context = dict(identity, work=work, output=output, session=session, previous_session=session, mode="FULL",
                   calendar=exchange_calendar(market), executed_engines=1, reused_engines=0)
    stages = (Stage("session_checkpoint", _checkpoint), Stage("position_history", record, ("session_checkpoint",)),
              Stage("workbook", _workbook, ("position_history",)), Stage("certify", _certify, ("workbook",)))
    results = _execute(context, stages)
    assert all(result["status"] == "PASS" for result in results.values()), results
    observation = read(work, market, session)["positions"][pid]
    assert observation["ticker"] == ticker
    assert observation["stop_type"] == "trailing"
    assert observation["first_target_reached_session"] == session
    assert observation["giveback_pp"] == pytest.approx(6.0)
    record(context)
    revisions = work / "reports/context" / f"shadow_position_history_{market}" / session
    assert len(list(revisions.glob("*.json"))) == 1
    publication = publish(tmp_path, output, dict(identity, status="SHADOW_CERTIFIED", market_data_asof=session,
                                                 workbook_sha256=context["workbook_sha256"]))
    assert discover(tmp_path, market, "new")["sha256"] == publication["sha256"]


def test_stop_review_detects_loosening_without_changing_target_history():
    market, asof, session = "india", "2026-11-26", "2026-11-26"
    identity = dict(market=market, asof=asof)
    basis = "dynamic_risk_v2"
    row = dict(position_id="episode", entry_date="2026-11-20", entry_price=100, current_price=105,
               market_data_asof=session, stop=101, stop_basis=basis, target=107)
    prior = {"positions": {"episode": dict(entry_date="2026-11-20", entry_price=100, effective_stop=103,
                                          stop_source=basis, price_current=True, target=107,
                                          first_target_reached_session="2026-11-25")}}
    report = position_snapshot(dict(identity, market_data_asof=session, current=[row], exits=[]),
                               dict(identity, monotonic=True, updates=[]), dict(identity, decisions=[]),
                               market, asof, session, prior=prior)["positions"]["episode"]
    assert report["monotonic_violation"] is True
    assert report["first_target_reached_session"] == "2026-11-25"
    assert report["effective_stop"] == 101


def test_regime_cache_fails_closed_on_input_and_output_changes(tmp_path):
    receipt, output = tmp_path / "receipt.json", tmp_path / "regime.json"
    session = "2026-11-25"
    _write(tmp_path, "regime.json", {"market": "USA", "status": "OK", "regimes": {session: "NEUTRAL"}})
    cached = (receipt, output, {"input_sha256": "before"})
    seal_regime(cached, "usa", session)
    assert reuse_regime(cached, "usa", session)
    assert not reuse_regime((receipt, output, {"input_sha256": "after"}), "usa", session)
    output.write_text("invalid", encoding="utf-8")
    assert not reuse_regime(cached, "usa", session)


def test_price_import_preserves_saved_rows_and_deduplicates(tmp_path):
    import pandas as pd

    incoming, accepted = tmp_path / "incoming.parquet", tmp_path / "accepted.parquet"
    days = pd.date_range("2026-11-02", periods=8, freq="B")
    data = pd.DataFrame({"close": list(range(100, 108))}, index=days)
    data.iloc[:-1].to_parquet(accepted)
    data.iloc[2:].to_parquet(incoming)
    assert _append_price_history(incoming, accepted, days[-1].date().isoformat()) == 1
    assert _append_price_history(incoming, accepted, days[-1].date().isoformat()) == 0
    pd.testing.assert_frame_equal(pd.read_parquet(accepted), data, check_freq=False)


def test_simulated_accounting_uses_dated_opening_cash_and_rejects_duplicate_fills():
    opening = dict(market="usa", opening_session="2026-11-24", mark_session="2026-11-25", source="fixture",
                   cash=50.0, shares={"BRK.B": 2.0}, close_prices={"BRK.B": 100.0})
    fill = dict(txn_id="one", ticker="BRK.B", market="usa", fill_date="2026-11-25", action="DECREASE",
                side="LONG", shares=1.0, filled_notional=100.0, commission_amount=1.0)
    result = reconcile(opening, [fill], "usa", "2026-11-25", "2026-11-24")
    assert result["ending_cash"] == 149
    assert result["ending_equity"] == 249
    with pytest.raises(ValueError, match="duplicate"):
        reconcile(opening, [fill, fill], "usa", "2026-11-25", "2026-11-24")
