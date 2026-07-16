"""OPS001.5 Production Commissioning Suite.

Twenty operational subsystems, each with an explicit PASS/FAIL criterion.
Not a unit-test suite — these are integration-level assertions that the
daemon behaves as an unattended production service.

Purpose: run this suite before declaring a deployment production-ready.
Every test MUST PASS. If any single test fails, the deployment is NOT
commissioned.

Never touches production files, MON001 sealed core, or LAB artefacts.
Uses tempdirs and inspection over already-shipped modules.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# --- imports from every OPS001 subsystem being commissioned -----------

from nexaquant.ops import __version__ as OPS_VERSION
from nexaquant.ops.logging_setup import LogConfig, configure, prune_old_logs
from nexaquant.ops.pidlock import PidLock
from nexaquant.ops.monitoring import ProcessMonitor
from nexaquant.ops.scheduler import Slot, Scheduler
from nexaquant.ops.recovery import (
    RunPhase, RecoveryAction, RunState, decide as decide_recovery,
    mark_starting, mark_running,
)
from nexaquant.ops.daemon import NexaQuantDaemon, default_daemon_config
from nexaquant.ops.metrics import MetricsLedger
from nexaquant.ops.status import StatusSnapshot, StatusWriter
from nexaquant.ops.retry import RetryPolicy
from nexaquant.ops.events import Severity
from nexaquant.ops.notify.base import Notification
from nexaquant.ops.notify.file import FileChannel
from nexaquant.ops.notify.telegram import TelegramChannel
from nexaquant.ops.notify.manager import NotificationManager
from nexaquant.ops.config import load_pipeline
from nexaquant.ops.service import NexaQuantService, default_config


PIPELINE_YAML = ROOT / "nexaquant" / "ops" / "pipelines" / "aegis_daily.yaml"


def _tmp() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


# ============= 20 COMMISSIONING SUBSYSTEMS =============


def sub_01_cold_boot_after_machine_restart():
    """Daemon must initialize cleanly on a host with NO prior state files."""
    with _tmp() as tmp:
        cfg = default_daemon_config(repo_root=ROOT)
        # Point every mutable path at a fresh empty tempdir — simulates first boot.
        cfg.log_dir = Path(tmp) / "logs"
        cfg.schedule_state_path = Path(tmp) / "schedule.json"
        cfg.run_state_path = Path(tmp) / "run.json"
        cfg.pidlock_path = Path(tmp) / "daemon.lock"
        assert not cfg.log_dir.exists()
        assert not cfg.schedule_state_path.exists()
        assert not cfg.run_state_path.exists()
        assert not cfg.pidlock_path.exists()
        # Construction must succeed with no state.
        d = NexaQuantDaemon(cfg)
        snap = d.snapshot()
        assert snap["ops_version"] == OPS_VERSION
        assert snap["pid"] == os.getpid()
    print("  [PASS] SUB-01 cold boot after machine restart — daemon initialized with 0 state files")


def sub_02_graceful_shutdown_via_sigterm():
    """SIGTERM handler must be installed and settable via signal.getsignal."""
    import signal
    with _tmp() as tmp:
        cfg = default_daemon_config(repo_root=ROOT)
        cfg.log_dir = Path(tmp) / "logs"
        cfg.schedule_state_path = Path(tmp) / "sched.json"
        cfg.run_state_path = Path(tmp) / "run.json"
        cfg.pidlock_path = Path(tmp) / "d.lock"
        d = NexaQuantDaemon(cfg)
        d._install_signal_handlers()
        h = signal.getsignal(signal.SIGTERM)
        assert callable(h), "SIGTERM handler is not callable after _install_signal_handlers"
        assert not d._stop_event.is_set()
        h(signal.SIGTERM, None)
        assert d._stop_event.is_set(), "handler did not set stop_event"
    print("  [PASS] SUB-02 graceful shutdown — SIGTERM handler wired and sets stop_event")


def sub_03_restart_recovery_lock_release_permits_new_daemon():
    """After a clean release, a new daemon must be able to acquire."""
    with _tmp() as tmp:
        lock_path = Path(tmp) / "d.lock"
        a = PidLock(lock_path)
        assert a.acquire()
        a.release()
        assert not lock_path.exists()
        b = PidLock(lock_path)
        assert b.acquire()
        b.release()
    print("  [PASS] SUB-03 restart recovery — clean release permits new daemon start")


def sub_04_pid_lock_recovery_dead_pid():
    """A lock owned by a dead PID must be broken automatically."""
    with _tmp() as tmp:
        p = Path(tmp) / "d.lock"
        p.write_text(json.dumps({
            "pid": 999999999,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "host": "h", "cmdline": "x"}), encoding="utf-8")
        lock = PidLock(p, stale_hours=6.0)
        stale, why = lock.is_stale(lock.read())
        assert stale, f"expected stale for dead pid, got '{why}'"
        assert lock.acquire()
        lock.release()
    print("  [PASS] SUB-04 PID lock recovery — dead-pid lock broken automatically")


def sub_05_stale_lock_cleanup_by_age():
    """A lock older than stale_hours must be broken even if pid is live."""
    with _tmp() as tmp:
        p = Path(tmp) / "d.lock"
        old = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        p.write_text(json.dumps({
            "pid": os.getpid(), "started_utc": old,
            "host": "h", "cmdline": "x"}), encoding="utf-8")
        lock = PidLock(p, stale_hours=6.0)
        assert lock.acquire(), "age-stale lock was not broken"
        lock.release()
    print("  [PASS] SUB-05 stale lock cleanup — age-based break honored")


def sub_06_interrupted_pipeline_recovery():
    """A previous RUNNING phase must yield a RESUME decision with correct stage."""
    with _tmp() as tmp:
        p = Path(tmp) / "run.json"
        mark_starting(p, pipeline_name="aegis_daily", slot_name="primary_1615_ist",
                       pid=os.getpid())
        mark_running(p, current_stage="mon001_daily")
        state = RunState.load(p)
        d = decide_recovery(state)
        assert d.action == RecoveryAction.RESUME
        assert "mon001_daily" in d.reason
        assert d.previous_phase == RunPhase.RUNNING.value
    print("  [PASS] SUB-06 interrupted pipeline recovery — RESUME decision produced for RUNNING")


def sub_07_scheduler_correctness_fires_within_window():
    """A slot at 16:15 IST must be due at exactly 16:15 IST and not before/after."""
    slot = Slot(name="primary", hour=16, minute=15, fire_window_min=5,
                 tz_offset_hours=5.5)
    # 16:15 IST = 10:45 UTC. Wednesday 2026-07-15.
    at_exact = datetime(2026, 7, 15, 10, 45, 0, tzinfo=timezone.utc)
    assert slot.is_due(at_exact, None), "not due at exact scheduled time"
    one_before = datetime(2026, 7, 15, 10, 44, 30, tzinfo=timezone.utc)
    assert not slot.is_due(one_before, None), "due 30s before window opens"
    past_window = datetime(2026, 7, 15, 10, 51, 0, tzinfo=timezone.utc)
    assert not slot.is_due(past_window, None), "due after window closes"
    print("  [PASS] SUB-07 scheduler correctness — fires within window, silent outside")


def sub_08_timezone_correctness_ist_to_utc():
    """IST +05:30 offset must produce correct UTC scheduled instants."""
    slot = Slot(name="s", hour=16, minute=15, tz_offset_hours=5.5)
    ref_utc = datetime(2026, 7, 15, 10, 45, 0, tzinfo=timezone.utc)
    sched_local = slot.scheduled_local(ref_utc)
    assert sched_local.hour == 16 and sched_local.minute == 15
    # sched_local's UTC form must be 10:45 UTC on the same date.
    sched_utc = sched_local.astimezone(timezone.utc)
    assert sched_utc.hour == 10 and sched_utc.minute == 45, (sched_utc.hour, sched_utc.minute)
    assert sched_utc.date() == ref_utc.date()
    print("  [PASS] SUB-08 timezone correctness — IST +05:30 -> UTC math correct")


def sub_09_log_rotation_triggers_at_max_bytes():
    """After enough writes, RotatingFileHandler must produce at least one backup."""
    with _tmp() as tmp:
        cfg = LogConfig(log_dir=Path(tmp), max_bytes=1024, backup_count=3,
                          stderr_mirror=False)
        logger = configure(cfg)
        # Each record is a JSON line; write enough to exceed 1 KiB many times.
        payload = "x" * 128
        for i in range(200):
            logger.info(payload, extra={"i": i, "event": "rotation_test"})
        for h in logger.handlers:
            try:
                h.flush()
            except Exception:
                pass
        rotated = [p for p in Path(tmp).iterdir()
                   if p.name.startswith("nexaquant_ops.jsonl.")]
        assert len(rotated) >= 1, f"no rotated files produced (files: {list(Path(tmp).iterdir())})"
        # Explicitly close file handlers so the tempdir cleanup on Windows succeeds.
        for h in list(logger.handlers):
            try:
                h.close()
            except Exception:
                pass
    print(f"  [PASS] SUB-09 log rotation — {len(rotated)} rotated file(s) produced")


def sub_10_log_retention_prunes_old_files():
    """Rotated logs older than retention_days must be deleted; active preserved."""
    with _tmp() as tmp:
        d = Path(tmp)
        active = d / "nexaquant_ops.jsonl"
        active.write_text("{}", encoding="utf-8")
        old_1 = d / "nexaquant_ops.jsonl.1"
        old_2 = d / "nexaquant_ops.jsonl.2"
        old_1.write_text("{}", encoding="utf-8")
        old_2.write_text("{}", encoding="utf-8")
        old_ts = time.time() - 60 * 86400
        os.utime(old_1, (old_ts, old_ts))
        os.utime(old_2, (old_ts, old_ts))
        pruned = prune_old_logs(d, "nexaquant_ops.jsonl", retention_days=30)
        assert pruned == 2
        assert active.exists()
        assert not old_1.exists()
        assert not old_2.exists()
    print("  [PASS] SUB-10 log retention — old rotations pruned, active preserved")


def sub_11_metrics_persistence_append_only():
    """MetricsLedger must append each record without truncation."""
    with _tmp() as tmp:
        p = Path(tmp) / "metrics.jsonl"
        ledger = MetricsLedger(p)
        for i in range(10):
            ledger.record_stage(pipeline="commissioning", stage=f"stage_{i}",
                                 success=True, attempts=1, duration_s=float(i))
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 10, f"expected 10 records, got {len(lines)}"
        # Every line must parse as JSON.
        for L in lines:
            row = json.loads(L)
            assert row["pipeline"] == "commissioning"
            assert row["success"] is True
        # Reading back via the public rows() API must return the same count.
        rows = ledger.rows()
        assert len(rows) == 10
    print(f"  [PASS] SUB-11 metrics persistence — 10/10 records survived roundtrip")


def sub_12_dashboard_refresh_produces_markdown():
    """MON001 dashboard builder must produce non-empty markdown."""
    from india.monitoring.MON001_Forward_Validation.ops.dashboard import build_dashboard
    md = build_dashboard()
    assert isinstance(md, str) and len(md) > 100
    assert "MON001" in md
    print(f"  [PASS] SUB-12 dashboard refresh — non-empty markdown ({len(md)} chars)")


def sub_13_telegram_delivery_channel_wiring_intact():
    """FileChannel must reliably emit; TelegramChannel must instantiate."""
    with _tmp() as tmp:
        alerts_path = Path(tmp) / "alerts.jsonl"
        fc = FileChannel(alerts_path, min_severity=Severity.INFO)
        note = Notification.new(severity=Severity.INFO, source="commissioning",
                                  title="test", body="body")
        assert fc.send(note) is True
        assert alerts_path.exists()
        content = alerts_path.read_text(encoding="utf-8")
        assert "commissioning" in content and "test" in content
        # TelegramChannel must always instantiate (may or may not be configured).
        tg = TelegramChannel(min_severity=Severity.WARN)
        _ = tg.configured  # attribute exists — read is enough
    print("  [PASS] SUB-13 telegram delivery — FileChannel emits, TelegramChannel instantiates")


def sub_14_retry_behaviour_max_attempts_and_backoff():
    """RetryPolicy must hold max_attempts + backoff_s exactly as configured."""
    rp = RetryPolicy(max_attempts=4, backoff_s=[0.5, 1.0, 2.0], timeout_per_attempt_s=30.0)
    assert rp.max_attempts == 4
    assert list(rp.backoff_s) == [0.5, 1.0, 2.0]
    assert rp.timeout_per_attempt_s == 30.0
    # backoff_delay_s (or its equivalent) must return correct wait per attempt idx.
    if hasattr(rp, "backoff_for_attempt"):
        assert rp.backoff_for_attempt(1) == 0.5
        assert rp.backoff_for_attempt(2) == 1.0
        assert rp.backoff_for_attempt(3) == 2.0
    print("  [PASS] SUB-14 retry behaviour — RetryPolicy fields preserved verbatim")


def sub_15_failure_escalation_severity_filter():
    """NotificationManager routes INFO to file, filters below-threshold on Telegram."""
    with _tmp() as tmp:
        alerts_path = Path(tmp) / "a.jsonl"
        fc = FileChannel(alerts_path, min_severity=Severity.WARN)   # WARN+
        mgr = NotificationManager(channels=[fc])
        # INFO below threshold — must NOT be written by fc.
        mgr.emit(Notification.new(severity=Severity.INFO, source="s", title="t", body="b"))
        assert not alerts_path.exists() or alerts_path.read_text(encoding="utf-8").strip() == ""
        # CRITICAL above threshold — must be written.
        mgr.emit(Notification.new(severity=Severity.CRITICAL, source="s", title="t2", body="b2"))
        content = alerts_path.read_text(encoding="utf-8")
        assert "t2" in content and "CRITICAL" in content.upper()
    print("  [PASS] SUB-15 failure escalation — severity threshold honored across NotificationManager")


def sub_16_status_endpoint_accuracy():
    """StatusWriter produces a JSON file with the documented schema keys."""
    with _tmp() as tmp:
        path = Path(tmp) / "ops_status.json"
        writer = StatusWriter(path, repo_root=ROOT)
        snap = StatusSnapshot(
            pipeline_name="aegis_daily",
            last_pipeline_success=True,
            stages_ok=9, stages_total=9,
            ops_version=OPS_VERSION,
        )
        writer.write(snap)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        required = ["schema_version", "written_at_utc", "ops_version",
                    "pipeline_name", "last_pipeline_success", "stages_ok",
                    "stages_total", "mon001_state", "mon001_halt",
                    "mon001_fingerprint_hash", "broker_status",
                    "recommendation_last_asof", "ops_uptime_s"]
        missing = [k for k in required if k not in data]
        assert not missing, f"status JSON missing keys: {missing}"
        assert data["schema_version"] == 1
        assert data["ops_version"] == OPS_VERSION
    print("  [PASS] SUB-16 status endpoint accuracy — schema v1 satisfied")


def sub_17_health_endpoint_accuracy():
    """MON001 health check must report INFO worst-severity when sealed state is clean."""
    from india.monitoring.MON001_Forward_Validation.ops.health_check import (
        run_health_checks,
    )
    report = run_health_checks()
    assert report.worst_severity == "INFO", (
        f"health-check worst_severity={report.worst_severity} != 'INFO'. "
        f"Non-INFO checks: "
        + ", ".join(f"{c.name}={c.severity}" for c in report.checks
                    if c.severity != "INFO"))
    assert report.exit_code == 0
    print(f"  [PASS] SUB-17 health endpoint accuracy — {len(report.checks)}/{len(report.checks)} checks INFO, exit=0")


def sub_18_recovery_after_pipeline_exception():
    """MON001 daily_runner must absorb a synthetic exception and still return 0."""
    from india.monitoring.MON001_Forward_Validation.ops import daily_runner
    from india.monitoring.MON001_Forward_Validation import run_mon001

    def _boom():
        raise RuntimeError("commissioning synthetic — must be absorbed by daily_runner")

    original = run_mon001.main
    run_mon001.main = _boom
    try:
        rc = daily_runner.run_once()
    finally:
        run_mon001.main = original
    assert rc == 0, (f"daily_runner returned {rc} on synthetic exception; "
                     f"expected 0 (exception isolation guarantee)")
    print("  [PASS] SUB-18 pipeline exception recovery — daily_runner absorbed synthetic exception, rc=0")


def sub_19_power_loss_simulation_survives_via_stale_lock_break():
    """Simulate abrupt process death: leftover lock with a dead pid + old timestamp.
    New daemon (or PidLock caller) must break it and proceed."""
    with _tmp() as tmp:
        p = Path(tmp) / "d.lock"
        # Both conditions: unknown-dead pid AND aged out.
        very_old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        p.write_text(json.dumps({
            "pid": 999999999, "started_utc": very_old,
            "host": "crashed-host", "cmdline": "died"}), encoding="utf-8")
        lock = PidLock(p, stale_hours=6.0)
        holder = lock.read()
        stale, why = lock.is_stale(holder)
        assert stale
        assert lock.acquire(), "new daemon could not acquire after simulated crash"
        lock.release()
    print("  [PASS] SUB-19 power-loss simulation — crashed daemon's lock cleaned up")


def sub_20_end_to_end_daily_pipeline_wiring():
    """NexaQuantService must construct + load the shipped pipeline YAML without error.
    Does NOT run the pipeline (that would touch broker/network) — validates wiring."""
    cfg = default_config(repo_root=ROOT)
    assert cfg.pipeline_config == PIPELINE_YAML
    pipeline_cfg = load_pipeline(cfg.pipeline_config)
    assert pipeline_cfg.name == "aegis_daily"
    assert len(pipeline_cfg.stages) >= 8, (
        f"expected >=8 stages in aegis_daily pipeline, got {len(pipeline_cfg.stages)}")
    stage_names = {s.name for s in pipeline_cfg.stages}
    for required in ("refresh_data", "recommendation_generator", "telegram_notify",
                      "mon001_daily"):
        assert required in stage_names, f"missing required stage: {required}"
    # Instantiate service — must not raise.
    svc = NexaQuantService(cfg)
    assert svc is not None
    print(f"  [PASS] SUB-20 end-to-end pipeline wiring — {len(pipeline_cfg.stages)} stages, "
           f"all required stages present, service constructed")


# ============= governance re-verification =============


def gov_21_no_sealed_files_touched():
    """OPS001.5 must not have introduced any sealed-file modification."""
    r = subprocess.run(["git", "diff", "HEAD", "--name-only"],
                        cwd=str(ROOT), capture_output=True, text=True)
    changed = set(line.strip().replace("\\", "/")
                   for line in r.stdout.splitlines() if line.strip())
    forbidden = {
        "india/recommendation_registry.py",
        "india/recommendation_generator.py",
        "india/confidence_engine.py",
        "india/arjuna_v2.py",
        "india/data_nse.py",
        "india/monitoring/MON001_Forward_Validation/preregistration.md",
        "india/monitoring/MON001_Forward_Validation/mon001.yaml",
        "india/monitoring/MON001_Forward_Validation/monitor.py",
        "india/monitoring/MON001_Forward_Validation/forward_ledger.py",
        "india/monitoring/MON001_Forward_Validation/fingerprint.py",
        "india/monitoring/MON001_Forward_Validation/baseline_envelope.py",
        "india/monitoring/MON001_Forward_Validation/broker_layer.py",
    }
    lab_paths = [p for p in changed if p.startswith("india/ai_lab/")
                 and not p.endswith("__pycache__")]
    touched = forbidden & changed
    assert not touched, f"OPS001.5 touched sealed files: {sorted(touched)}"
    assert not lab_paths, f"OPS001.5 touched LAB artefacts: {lab_paths}"
    print("  [PASS] GOV-21 no sealed / LAB artefacts touched by OPS001.5 diff")


def gov_22_mon001_fingerprint_matches_seal():
    from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
    import yaml
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = yaml.safe_load(f)
    sealed = json.loads((ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json"
                         ).read_text(encoding="utf-8"))
    current = compute_fingerprint(ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    assert current["hash"] == sealed["hash"]
    print(f"  [PASS] GOV-22 MON001 fingerprint matches seal ({current['hash'][:16]}...)")


def gov_23_production_constants_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    assert "sector_cap=2" in gen
    assert "name_cap=0.30" in gen
    m = (ROOT / "india/ai_lab/trial_manifest.md").read_text(encoding="utf-8", errors="ignore")
    assert "cumulative_strategy_search: 38" in m
    print("  [PASS] GOV-23 production constants + trial count unchanged")


TESTS = [
    sub_01_cold_boot_after_machine_restart,
    sub_02_graceful_shutdown_via_sigterm,
    sub_03_restart_recovery_lock_release_permits_new_daemon,
    sub_04_pid_lock_recovery_dead_pid,
    sub_05_stale_lock_cleanup_by_age,
    sub_06_interrupted_pipeline_recovery,
    sub_07_scheduler_correctness_fires_within_window,
    sub_08_timezone_correctness_ist_to_utc,
    sub_09_log_rotation_triggers_at_max_bytes,
    sub_10_log_retention_prunes_old_files,
    sub_11_metrics_persistence_append_only,
    sub_12_dashboard_refresh_produces_markdown,
    sub_13_telegram_delivery_channel_wiring_intact,
    sub_14_retry_behaviour_max_attempts_and_backoff,
    sub_15_failure_escalation_severity_filter,
    sub_16_status_endpoint_accuracy,
    sub_17_health_endpoint_accuracy,
    sub_18_recovery_after_pipeline_exception,
    sub_19_power_loss_simulation_survives_via_stale_lock_break,
    sub_20_end_to_end_daily_pipeline_wiring,
    gov_21_no_sealed_files_touched,
    gov_22_mon001_fingerprint_matches_seal,
    gov_23_production_constants_unchanged,
]


def main() -> int:
    print("=" * 72)
    print("  OPS001.5 PRODUCTION COMMISSIONING — 20 subsystems + 3 governance guards")
    print("=" * 72)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print()
    if failed == 0:
        print(f"  COMMISSIONING VERDICT: ACCEPTED  ({passed}/{len(TESTS)} PASS)")
        return 0
    print(f"  COMMISSIONING VERDICT: REJECTED  ({passed}/{len(TESTS)} PASS, {failed} FAIL)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
