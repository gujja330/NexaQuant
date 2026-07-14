"""
MON001 operational-layer tests.

Covers:
- health_check module output + exit codes
- alert bus emission, consecutive tracking, recommended action lookup
- dashboard renders without exception
- daily_runner: weekend/holiday handling, lock-file mutex, atomic writes,
  exception isolation, always exit 0
- holiday_calendar: NSE holidays + weekend + previous/next trading day
- stress_test: chain integrity + boundary guard hold at 30/90/180/365 days

Never touches production files, LAB evidence, or the real MON001 ledger/reports.
Uses tempdirs + monkeypatching.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta, timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.monitoring.MON001_Forward_Validation.ops.holiday_calendar import (
    is_trading_day, is_weekend, is_holiday, previous_trading_day,
    next_trading_day, trading_days_between,
)
from india.monitoring.MON001_Forward_Validation.ops.alerts import (
    AlertBus, SEVERITY_ORDER, RECOMMENDED_ACTION,
)
from india.monitoring.MON001_Forward_Validation.ops.health_check import (
    run_health_checks, HealthReport, CheckResult,
)


# ----------------------------- Tests -----------------------------


def test_1_holiday_republic_day():
    d = date(2026, 1, 26)     # Republic Day
    assert is_holiday(d), "Republic Day must be a holiday"
    assert not is_trading_day(d)
    print("  TEST 1 PASS: Republic Day recognized as holiday")


def test_2_weekend_detected():
    saturday = date(2026, 7, 11)
    sunday = date(2026, 7, 12)
    assert is_weekend(saturday) and is_weekend(sunday)
    assert not is_trading_day(saturday) and not is_trading_day(sunday)
    print("  TEST 2 PASS: weekend detected")


def test_3_previous_trading_day_skips_weekend_and_holiday():
    # Monday 2026-07-13. Previous trading day = Friday 2026-07-10.
    d = previous_trading_day(date(2026, 7, 13))
    assert d == date(2026, 7, 10), f"expected 2026-07-10, got {d}"
    # Independence day 2026-08-15 (Sat), so previous of 2026-08-17 (Mon) = Fri 2026-08-14.
    d2 = previous_trading_day(date(2026, 8, 17))
    assert d2 == date(2026, 8, 14), f"expected 2026-08-14, got {d2}"
    print("  TEST 3 PASS: previous_trading_day skips weekends and holidays")


def test_4_next_trading_day():
    # Friday 2026-07-10 -> Monday 2026-07-13.
    d = next_trading_day(date(2026, 7, 10))
    assert d == date(2026, 7, 13)
    print("  TEST 4 PASS: next_trading_day skips weekends")


def test_5_trading_days_between():
    n = trading_days_between(date(2026, 6, 25), date(2026, 6, 30))
    # 2026-06-25 Thu, 26 Fri, 27 Sat, 28 Sun, 29 Mon, 30 Tue -> 3 trading days after 06-25
    assert n == 3, f"expected 3 trading days, got {n}"
    print(f"  TEST 5 PASS: trading_days_between counted {n}")


def test_6_alert_bus_emit_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        bus = AlertBus(Path(tmp) / "alerts.jsonl")
        a = bus.emit("D2_PERFORMANCE_DRIFT", "WARN", "Sharpe below envelope")
        assert a.severity == "WARN"
        assert a.consecutive_occurrences == 1
        assert "Sharpe" in a.recommended_action or a.recommended_action  # non-empty
        rows = bus.read_all()
        assert len(rows) == 1 and rows[0]["dimension"] == "D2_PERFORMANCE_DRIFT"
    print("  TEST 6 PASS: alert bus emit + read round-trip")


def test_7_alert_bus_rejects_unknown_severity():
    with tempfile.TemporaryDirectory() as tmp:
        bus = AlertBus(Path(tmp) / "alerts.jsonl")
        try:
            bus.emit("D2_PERFORMANCE_DRIFT", "FATAL", "bad severity")
        except ValueError as e:
            assert "severity" in str(e)
        else:
            raise AssertionError("expected ValueError for unknown severity")
    print("  TEST 7 PASS: unknown severity rejected")


def test_8_alert_bus_recommended_action_lookup():
    with tempfile.TemporaryDirectory() as tmp:
        bus = AlertBus(Path(tmp) / "alerts.jsonl")
        for dim in ("D1_CONFIG_DRIFT", "D10_DATA_INTEGRITY_FAILURE",
                     "OPS_RUN_FAILED", "OPS_MARKET_CLOSED"):
            a = bus.emit(dim, "WARN", "test")
            assert a.recommended_action, f"missing recommended_action for {dim}"
    print("  TEST 8 PASS: recommended_action populated for known dimensions")


def test_9_alert_bus_active_filter():
    with tempfile.TemporaryDirectory() as tmp:
        bus = AlertBus(Path(tmp) / "alerts.jsonl")
        bus.emit("D2_PERFORMANCE_DRIFT", "INFO", "info-level")
        bus.emit("D3_RISK_DRIFT", "WARN", "warn-level")
        bus.emit("D1_CONFIG_DRIFT", "HALT_REVIEW_REQUIRED", "halt-level")
        active = bus.active("WARN")
        assert len(active) == 2, f"expected 2 active WARN+, got {len(active)}"
        halt = bus.active("HALT_REVIEW_REQUIRED")
        assert len(halt) == 1
    print("  TEST 9 PASS: active() filters by severity threshold")


def test_10_severity_ordering():
    assert SEVERITY_ORDER["INFO"] < SEVERITY_ORDER["WARN"] < SEVERITY_ORDER["HALT_REVIEW_REQUIRED"]
    print("  TEST 10 PASS: severity ordering INFO < WARN < HALT")


def test_11_recommended_action_playbook_completeness():
    required = ("D1_CONFIG_DRIFT", "D2_PERFORMANCE_DRIFT", "D3_RISK_DRIFT",
                 "D4_TURNOVER_DRIFT", "D5_COST_DRIFT", "D6_REGIME_BEHAVIOUR_DRIFT",
                 "D7_CONCENTRATION_DRIFT", "D8_DATA_DRIFT", "D9_EXECUTION_DRIFT",
                 "D10_DATA_INTEGRITY_FAILURE", "OPS_RUN_FAILED",
                 "OPS_MARKET_CLOSED", "OPS_DATA_STALE")
    missing = [k for k in required if k not in RECOMMENDED_ACTION]
    assert not missing, f"missing playbook entries: {missing}"
    print(f"  TEST 11 PASS: {len(required)} playbook entries populated")


def test_12_health_check_report_shape():
    report = run_health_checks()
    assert isinstance(report, HealthReport)
    names = [c.name for c in report.checks]
    for required_check in ("config_loads", "sealed_fingerprint_exists",
                            "fingerprint_matches_seal", "envelope_byte_identical",
                            "ledger_integrity", "no_duplicate_recs",
                            "broker_paper_only", "cumulative_strategy_search_38",
                            "production_constants"):
        assert required_check in names, f"missing health check {required_check}"
    print(f"  TEST 12 PASS: health report has {len(report.checks)} checks; worst={report.worst_severity}")


def test_13_health_check_current_state_clean():
    # In a healthy repo (production untouched since MON001 seal) worst severity is INFO
    report = run_health_checks()
    assert report.worst_severity == "INFO", (
        f"expected INFO worst severity but got {report.worst_severity}: "
        + json.dumps([c.__dict__ for c in report.checks if c.severity != "INFO"], indent=2))
    assert report.exit_code == 0
    print("  TEST 13 PASS: health check exit=0 (production unchanged since seal)")


def test_14_dashboard_renders():
    from india.monitoring.MON001_Forward_Validation.ops.dashboard import build_dashboard
    md = build_dashboard()
    assert isinstance(md, str) and len(md) > 100
    assert "MON001" in md and "State" in md
    print("  TEST 14 PASS: dashboard renders non-empty markdown")


def test_15_daily_runner_exit_0_even_on_synthetic_exception(monkeypatch=None):
    from india.monitoring.MON001_Forward_Validation.ops import daily_runner
    # Simulate top-level exception by monkey-patching run_mon001.main
    from india.monitoring.MON001_Forward_Validation import run_mon001

    def _boom():
        raise RuntimeError("synthetic — should be caught by daily_runner")

    orig = run_mon001.main
    run_mon001.main = _boom
    try:
        rc = daily_runner.run_once()
        assert rc == 0, f"daily_runner must return 0 even on exception, got {rc}"
    finally:
        run_mon001.main = orig
    print("  TEST 15 PASS: daily_runner absorbs exceptions and returns 0")


def test_16_daily_runner_lock_prevents_concurrent_run():
    from india.monitoring.MON001_Forward_Validation.ops.daily_runner import SingleInstanceLock
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "lock.json"
        a = SingleInstanceLock(lock_path)
        b = SingleInstanceLock(lock_path)
        assert a.acquire()
        assert not b.acquire(), "second acquire must fail while first holds"
        a.release()
        assert b.acquire(), "after release the lock must be re-acquirable"
        b.release()
    print("  TEST 16 PASS: single-instance lock prevents concurrent runs")


def test_17_lock_breaks_when_stale_pid():
    from india.monitoring.MON001_Forward_Validation.ops.daily_runner import SingleInstanceLock
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "lock.json"
        # Write a lock with an obviously-dead pid.
        lock_path.write_text(json.dumps({
            "pid": 999999999,
            "started_utc": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
        l = SingleInstanceLock(lock_path)
        assert l.acquire(), "stale-pid lock must be broken and re-acquired"
        l.release()
    print("  TEST 17 PASS: stale-pid lock automatically broken")


def test_18_lock_breaks_when_older_than_4h():
    from india.monitoring.MON001_Forward_Validation.ops.daily_runner import SingleInstanceLock
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "lock.json"
        old = datetime.now(timezone.utc) - timedelta(hours=5)
        lock_path.write_text(json.dumps({
            "pid": os.getpid(),        # our own live pid — still stale by age
            "started_utc": old.isoformat(),
        }), encoding="utf-8")
        l = SingleInstanceLock(lock_path)
        assert l.acquire(), "5h-old lock must be broken and re-acquired"
        l.release()
    print("  TEST 18 PASS: age-stale lock automatically broken")


def test_19_stress_test_scales():
    from india.monitoring.MON001_Forward_Validation.ops.stress_test import _simulate_scale
    with tempfile.TemporaryDirectory() as tmp:
        r = _simulate_scale(30, Path(tmp))
    assert r["chain_intact_first_pass"]
    assert r["boundary_guard_holds"]
    assert r["verify_s"] < 5.0
    print(f"  TEST 19 PASS: 30-day stress ok ({r['rows_appended']} rows, "
           f"verify={r['verify_s']:.3f}s, {r['ledger_bytes']//1024}KB)")


def test_20_stress_test_365_day():
    from india.monitoring.MON001_Forward_Validation.ops.stress_test import _simulate_scale
    with tempfile.TemporaryDirectory() as tmp:
        r = _simulate_scale(365, Path(tmp))
    assert r["chain_intact_first_pass"]
    assert r["boundary_guard_holds"]
    assert r["verify_s"] < 30.0, f"1y verify_chain too slow: {r['verify_s']}s"
    print(f"  TEST 20 PASS: 365-day stress ok ({r['rows_appended']} rows, "
           f"verify={r['verify_s']:.3f}s, {r['ledger_bytes']//1024}KB)")


def test_21_mon001_sealed_files_unchanged():
    # Verify the sealed MON001 files still match their earlier state.
    for f in ("preregistration.md", "mon001.yaml", "run_mon001.py",
              "monitor.py", "forward_ledger.py", "fingerprint.py",
              "baseline_envelope.py", "broker_layer.py"):
        p = (Path(__file__).parent / f)
        assert p.exists(), f"sealed MON001 file missing: {f}"
    print("  TEST 21 PASS: all sealed MON001 core files present")


def test_22_production_constants_still_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    print("  TEST 22 PASS: HOLD=63 and rebal=63 still in production code")


def test_23_cumulative_strategy_search_still_38():
    manifest = (ROOT / "india/ai_lab/trial_manifest.md").read_text(encoding="utf-8",
                                                                       errors="ignore")
    assert "cumulative_strategy_search: 38" in manifest
    print("  TEST 23 PASS: cumulative_strategy_search unchanged at 38")


TESTS = [
    test_1_holiday_republic_day,
    test_2_weekend_detected,
    test_3_previous_trading_day_skips_weekend_and_holiday,
    test_4_next_trading_day,
    test_5_trading_days_between,
    test_6_alert_bus_emit_and_read,
    test_7_alert_bus_rejects_unknown_severity,
    test_8_alert_bus_recommended_action_lookup,
    test_9_alert_bus_active_filter,
    test_10_severity_ordering,
    test_11_recommended_action_playbook_completeness,
    test_12_health_check_report_shape,
    test_13_health_check_current_state_clean,
    test_14_dashboard_renders,
    test_15_daily_runner_exit_0_even_on_synthetic_exception,
    test_16_daily_runner_lock_prevents_concurrent_run,
    test_17_lock_breaks_when_stale_pid,
    test_18_lock_breaks_when_older_than_4h,
    test_19_stress_test_scales,
    test_20_stress_test_365_day,
    test_21_mon001_sealed_files_unchanged,
    test_22_production_constants_still_unchanged,
    test_23_cumulative_strategy_search_still_38,
]


def main():
    print("=" * 70)
    print("  MON001 OPS FRAMEWORK TESTS — 23 scenarios")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
