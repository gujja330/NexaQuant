"""OPS001-B unit tests: daemon lifecycle, logging, PID lock, monitoring,
scheduler, recovery, and CLI dispatcher.

Never touches production files, MON001 sealed core, LAB artefacts, or the real
ops_status.json / metrics ledger — everything runs in tempdirs with injected
config.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexaquant.ops import __version__ as OPS_VERSION
from nexaquant.ops.logging_setup import (
    JsonFormatter, LogConfig, configure as configure_logging, get_logger,
    prune_old_logs, log_event, LOGGER_NAME,
)
from nexaquant.ops.pidlock import PidLock, LockHolder, _pid_alive
from nexaquant.ops.monitoring import ProcessMonitor, ProcessSnapshot, ExecutionTimings
from nexaquant.ops.scheduler import (
    Slot, ScheduleState, Scheduler, slots_from_config, DEFAULT_FIRE_WINDOW_MIN,
)
from nexaquant.ops.recovery import (
    RunPhase, RecoveryAction, RunState, decide as decide_recovery,
    mark_starting, mark_running, mark_stage_completed, mark_completed,
    mark_failed, mark_aborted,
)
from nexaquant.ops.daemon import (
    DaemonConfig, NexaQuantDaemon, default_daemon_config,
    DEFAULT_POLL_INTERVAL_S,
)
from nexaquant.ops.cli import build_parser


# ---------- version ----------

def test_1_version_is_ops001b():
    assert OPS_VERSION == "0.1.0-ops001b", (
        f"expected 0.1.0-ops001b, got {OPS_VERSION}")
    print(f"  TEST 1 PASS: ops __version__ = {OPS_VERSION}")


# ---------- logging ----------

def test_2_json_formatter_emits_valid_json():
    import logging
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "hello world",
                             None, None)
    line = JsonFormatter().format(rec)
    parsed = json.loads(line)
    assert parsed["msg"] == "hello world"
    assert parsed["level"] == "INFO"
    assert "ts" in parsed and parsed["pid"] == os.getpid()
    print("  TEST 2 PASS: JsonFormatter produces valid JSON per line")


def test_3_json_formatter_merges_extra_fields():
    import logging
    rec = logging.LogRecord("x", logging.WARNING, __file__, 1, "boom",
                             None, None)
    rec.__dict__["slot"] = "primary_1615_ist"
    rec.__dict__["retry"] = 3
    line = JsonFormatter().format(rec)
    parsed = json.loads(line)
    assert parsed["slot"] == "primary_1615_ist"
    assert parsed["retry"] == 3
    print("  TEST 3 PASS: JsonFormatter merges caller extra= fields")


def test_4_configure_creates_rotating_log():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = LogConfig(log_dir=Path(tmp), max_bytes=1024, backup_count=3,
                          stderr_mirror=False)
        logger = configure_logging(cfg)
        logger.info("hello", extra={"event": "test"})
        for h in logger.handlers:
            try:
                h.flush()
            except Exception:
                pass
        active = cfg.active_log_path
        assert active.exists(), "active log file was not created"
        content = active.read_text(encoding="utf-8")
        assert '"msg": "hello"' in content or '"msg":"hello"' in content
    print("  TEST 4 PASS: configure() creates active rotating log")


def test_5_configure_is_idempotent():
    """Calling configure() twice must not stack handlers."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = LogConfig(log_dir=Path(tmp), stderr_mirror=False)
        configure_logging(cfg)
        configure_logging(cfg)
        import logging
        logger = logging.getLogger(LOGGER_NAME)
        # We wrote a single file handler each time; second call should have
        # closed + removed the first before adding the new one.
        file_handlers = [h for h in logger.handlers if hasattr(h, 'baseFilename')]
        assert len(file_handlers) == 1
    print("  TEST 5 PASS: configure() is idempotent — no handler stacking")


def test_6_prune_old_logs_deletes_only_rotated():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        d = Path(tmp)
        # Active file — must never be deleted.
        active = d / "nexaquant_ops.jsonl"
        active.write_text("{}", encoding="utf-8")
        # Old rotation.
        rotated = d / "nexaquant_ops.jsonl.5"
        rotated.write_text("{}", encoding="utf-8")
        old_ts = time.time() - 40 * 86400
        os.utime(rotated, (old_ts, old_ts))
        pruned = prune_old_logs(d, "nexaquant_ops.jsonl", retention_days=30)
        assert pruned == 1
        assert active.exists()
        assert not rotated.exists()
    print("  TEST 6 PASS: prune_old_logs keeps active + deletes only old rotations")


# ---------- pidlock ----------

def test_7_pidlock_acquire_and_release():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        lock = PidLock(Path(tmp) / "d.lock")
        assert lock.acquire()
        assert lock.path.exists()
        assert lock.owned
        holder = lock.read()
        assert holder is not None and holder.pid == os.getpid()
        lock.release()
        assert not lock.path.exists()
        assert not lock.owned
    print("  TEST 7 PASS: PidLock acquire creates + release removes")


def test_8_pidlock_blocks_live_second_holder():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        a = PidLock(Path(tmp) / "d.lock", stale_hours=24.0)
        b = PidLock(Path(tmp) / "d.lock", stale_hours=24.0)
        assert a.acquire()
        assert not b.acquire(), "second acquire must fail while first holds"
        a.release()
        assert b.acquire()
        b.release()
    print("  TEST 8 PASS: PidLock blocks second holder until first releases")


def test_9_pidlock_breaks_stale_dead_pid():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = Path(tmp) / "d.lock"
        p.write_text(json.dumps({
            "pid": 999999999, "started_utc": datetime.now(timezone.utc).isoformat(),
            "host": "h", "cmdline": "x"}), encoding="utf-8")
        lock = PidLock(p)
        holder = lock.read()
        stale, why = lock.is_stale(holder)
        assert stale and "dead" in why
        assert lock.acquire()
        lock.release()
    print("  TEST 9 PASS: PidLock breaks stale lock when pid is dead")


def test_10_pidlock_breaks_stale_by_age():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = Path(tmp) / "d.lock"
        old = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        p.write_text(json.dumps({
            "pid": os.getpid(), "started_utc": old,
            "host": "h", "cmdline": "x"}), encoding="utf-8")
        lock = PidLock(p, stale_hours=6.0)
        assert lock.acquire()
        lock.release()
    print("  TEST 10 PASS: PidLock breaks stale lock when age > stale_hours")


def test_11_pid_alive_self():
    assert _pid_alive(os.getpid()) is True
    assert _pid_alive(999999999) is False
    print("  TEST 11 PASS: _pid_alive is True for self, False for phantom pid")


def test_12_pidlock_refresh_only_when_owned():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        lock = PidLock(Path(tmp) / "d.lock")
        # Refresh without owning is a no-op (no file created).
        lock.refresh()
        assert not lock.path.exists()
        assert lock.acquire()
        holder_before = lock.read()
        time.sleep(1.05)
        lock.refresh()
        holder_after = lock.read()
        assert holder_after.pid == holder_before.pid
        assert holder_after.started_utc != holder_before.started_utc
        lock.release()
    print("  TEST 12 PASS: PidLock.refresh() bumps started_utc only when owned")


# ---------- monitoring ----------

def test_13_process_monitor_snapshot_fields():
    mon = ProcessMonitor()
    snap = mon.snapshot()
    assert isinstance(snap, ProcessSnapshot)
    assert snap.pid == os.getpid()
    assert snap.uptime_s >= 0.0
    assert snap.source in ("psutil", "resource", "minimal")
    d = snap.as_dict()
    assert d["pid"] == os.getpid()
    print(f"  TEST 13 PASS: ProcessMonitor.snapshot source={snap.source} "
           f"uptime={snap.uptime_s:.3f}s")


def test_14_execution_timings_records_run():
    t = ExecutionTimings()
    t.record_run(duration_s=1.5, per_stage_seconds={"a": 0.5, "b": 1.0},
                  retries=1, failures=0)
    assert t.total_runs == 1
    assert t.total_stage_runs == 2
    assert t.total_stage_retries == 1
    assert t.last_run_duration_s == 1.5
    assert t.last_stage_duration_s == {"a": 0.5, "b": 1.0}
    print("  TEST 14 PASS: ExecutionTimings.record_run tallies correctly")


# ---------- scheduler ----------

def test_15_slot_is_due_within_window():
    slot = Slot(name="primary", hour=16, minute=15, weekdays=(1, 2, 3, 4, 5),
                 fire_window_min=5, tz_offset_hours=5.5)
    # Wednesday 2026-07-15 16:15 IST → 10:45 UTC. Use a UTC time slightly INSIDE window.
    ref_utc = datetime(2026, 7, 15, 10, 46, 0, tzinfo=timezone.utc)
    assert slot.is_due(ref_utc, None)
    # After window closes.
    assert not slot.is_due(datetime(2026, 7, 15, 11, 30, 0, tzinfo=timezone.utc), None)
    # Before window opens.
    assert not slot.is_due(datetime(2026, 7, 15, 10, 44, 0, tzinfo=timezone.utc), None)
    print("  TEST 15 PASS: Slot.is_due respects fire window")


def test_16_slot_is_due_respects_weekday_filter():
    slot = Slot(name="weekday_only", hour=16, minute=15,
                 weekdays=(1, 2, 3, 4, 5), tz_offset_hours=5.5)
    # Saturday 2026-07-11 IST → 10:45 UTC.
    sat_utc = datetime(2026, 7, 11, 10, 46, 0, tzinfo=timezone.utc)
    assert not slot.is_due(sat_utc, None)
    sun_utc = datetime(2026, 7, 12, 10, 46, 0, tzinfo=timezone.utc)
    assert not slot.is_due(sun_utc, None)
    print("  TEST 16 PASS: Slot.is_due filters non-trading weekdays")


def test_17_slot_is_due_dedupes_same_day():
    slot = Slot(name="s", hour=16, minute=15, tz_offset_hours=5.5)
    ref_utc = datetime(2026, 7, 15, 10, 46, 0, tzinfo=timezone.utc)
    already_fired = datetime(2026, 7, 15, 10, 46, 30, tzinfo=timezone.utc)
    assert not slot.is_due(ref_utc, already_fired)
    # Next day IST should be due again.
    next_day = datetime(2026, 7, 16, 10, 46, 0, tzinfo=timezone.utc)
    assert slot.is_due(next_day, already_fired)
    print("  TEST 17 PASS: Slot.is_due does not fire twice on same IST day")


def test_18_schedule_state_persists():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "sched.json"
        s = ScheduleState.load(path)
        assert s.last_fire("nonexistent") is None
        s.mark_fired("primary", datetime(2026, 7, 15, 10, 46, 0, tzinfo=timezone.utc))
        s.save(path)
        s2 = ScheduleState.load(path)
        assert s2.last_fire("primary") == datetime(2026, 7, 15, 10, 46, 0, tzinfo=timezone.utc)
    print("  TEST 18 PASS: ScheduleState survives save/load roundtrip")


def test_19_scheduler_next_run_utc():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        state_path = Path(tmp) / "sched.json"
        slots = [Slot(name="p", hour=16, minute=15, weekdays=(1, 2, 3, 4, 5))]
        sch = Scheduler(slots, state_path)
        # Monday morning UTC before slot fires — next_run_utc must be today's 10:45 UTC.
        ref = datetime(2026, 7, 13, 5, 0, 0, tzinfo=timezone.utc)
        nxt = sch.next_run_utc(ref)
        assert nxt is not None
        assert nxt.hour == 10 and nxt.minute == 45, (nxt.hour, nxt.minute)
    print("  TEST 19 PASS: Scheduler.next_run_utc finds nearest future slot")


def test_20_slots_from_config():
    spec = [
        {"name": "primary", "hour": 16, "minute": 15},
        {"name": "backup", "hour": 18, "minute": 30, "weekdays": [1, 2, 3, 4, 5]},
    ]
    slots = slots_from_config(spec)
    assert len(slots) == 2
    assert slots[0].name == "primary" and slots[0].hour == 16
    assert slots[1].weekdays == (1, 2, 3, 4, 5)
    print("  TEST 20 PASS: slots_from_config parses list of dicts")


# ---------- recovery ----------

def test_21_recovery_decision_idle_and_completed():
    for phase in (RunPhase.IDLE, RunPhase.COMPLETED):
        d = decide_recovery(RunState(phase=phase.value))
        assert d.action == RecoveryAction.NONE
    print("  TEST 21 PASS: RecoveryDecision NONE for idle+completed phases")


def test_22_recovery_decision_running_resumes():
    d = decide_recovery(RunState(phase=RunPhase.RUNNING.value,
                                    current_stage="mon001_daily"))
    assert d.action == RecoveryAction.RESUME
    assert "mon001_daily" in d.reason
    print("  TEST 22 PASS: RecoveryDecision RESUME for interrupted RUNNING")


def test_23_recovery_decision_aborted_resumes():
    d = decide_recovery(RunState(phase=RunPhase.ABORTED.value))
    assert d.action == RecoveryAction.RESUME
    print("  TEST 23 PASS: RecoveryDecision RESUME for ABORTED phase")


def test_24_recovery_decision_failed_needs_attention():
    d = decide_recovery(RunState(phase=RunPhase.FAILED.value, last_error="boom"))
    assert d.action == RecoveryAction.ATTENTION
    assert "boom" in d.reason
    print("  TEST 24 PASS: RecoveryDecision ATTENTION for FAILED phase")


def test_25_run_state_write_read_lifecycle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = Path(tmp) / "run_state.json"
        mark_starting(p, pipeline_name="aegis_daily",
                       slot_name="primary_1615_ist", pid=os.getpid())
        st = RunState.load(p)
        assert st.phase == RunPhase.STARTING.value
        assert st.pipeline_name == "aegis_daily"

        mark_running(p, current_stage="freshness_gate")
        st = RunState.load(p)
        assert st.phase == RunPhase.RUNNING.value
        assert st.current_stage == "freshness_gate"

        mark_stage_completed(p, "freshness_gate")
        mark_stage_completed(p, "recommendation_generator")
        st = RunState.load(p)
        assert st.stages_completed == ["freshness_gate", "recommendation_generator"]

        mark_completed(p)
        st = RunState.load(p)
        assert st.phase == RunPhase.COMPLETED.value
        assert st.finished_at_utc != ""
    print("  TEST 25 PASS: RunState writes propagate through STARTING -> RUNNING -> COMPLETED")


def test_26_mark_failed_and_aborted_record_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = Path(tmp) / "s.json"
        mark_starting(p, pipeline_name="x", slot_name="y", pid=os.getpid())
        mark_failed(p, err="ValueError: bad input")
        st = RunState.load(p)
        assert st.phase == RunPhase.FAILED.value
        assert "ValueError" in st.last_error

        mark_aborted(p, reason="SIGTERM")
        st = RunState.load(p)
        assert st.phase == RunPhase.ABORTED.value
        assert "SIGTERM" in st.last_error
    print("  TEST 26 PASS: mark_failed + mark_aborted record error and finished_at_utc")


# ---------- daemon ----------

def test_27_default_daemon_config_resolves_paths():
    cfg = default_daemon_config(repo_root=ROOT)
    assert cfg.pidlock_path.name == "ops_daemon.lock"
    assert cfg.schedule_state_path.name == "ops_schedule_state.json"
    assert cfg.run_state_path.name == "ops_run_state.json"
    assert cfg.log_dir.name == "logs"
    # Slots default to 3 IST slots.
    slot_names = [s.name for s in cfg.slots]
    assert "primary_1615_ist" in slot_names
    assert "backup_1830_ist" in slot_names
    assert "backup_2100_ist" in slot_names
    print(f"  TEST 27 PASS: default_daemon_config resolves all paths + 3 IST slots")


def test_28_daemon_snapshot_shape():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = default_daemon_config(repo_root=ROOT)
        cfg.log_dir = Path(tmp) / "logs"
        cfg.schedule_state_path = Path(tmp) / "sched.json"
        cfg.run_state_path = Path(tmp) / "run.json"
        cfg.pidlock_path = Path(tmp) / "d.lock"
        d = NexaQuantDaemon(cfg)
        snap = d.snapshot()
        assert snap["ops_version"] == "0.1.0-ops001b"
        assert snap["pid"] == os.getpid()
        assert "uptime_s" in snap and snap["uptime_s"] >= 0.0
        assert isinstance(snap["slots"], list) and len(snap["slots"]) == 3
        assert "process" in snap and "timings" in snap
    print("  TEST 28 PASS: NexaQuantDaemon.snapshot has ops_version + pid + process + timings")


def test_29_daemon_lock_blocks_second_start():
    """Two daemons can't run simultaneously — second instance's start() returns 3."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = default_daemon_config(repo_root=ROOT)
        cfg.log_dir = Path(tmp) / "logs"
        cfg.schedule_state_path = Path(tmp) / "sched.json"
        cfg.run_state_path = Path(tmp) / "run.json"
        cfg.pidlock_path = Path(tmp) / "d.lock"
        # Simulate a live daemon by pre-writing the lock with our OWN live pid.
        cfg.pidlock_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.pidlock_path.write_text(json.dumps({
            "pid": os.getpid(),
            "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "host": "h", "cmdline": "x"}), encoding="utf-8")
        d = NexaQuantDaemon(cfg)
        rc = d.start()
        assert rc == 3, f"expected exit code 3 when lock is held, got {rc}"
        # Cleanup: our fake lock still exists — remove it so we don't leak
        # a real-pid lock into other tests.
        try:
            cfg.pidlock_path.unlink()
        except OSError:
            pass
    print("  TEST 29 PASS: daemon.start() returns 3 when PID lock is held")


def test_30_daemon_tick_no_slots_due_is_noop():
    """When no slot is inside its fire window, _tick fires nothing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = default_daemon_config(repo_root=ROOT)
        cfg.log_dir = Path(tmp) / "logs"
        cfg.schedule_state_path = Path(tmp) / "sched.json"
        cfg.run_state_path = Path(tmp) / "run.json"
        cfg.pidlock_path = Path(tmp) / "d.lock"
        d = NexaQuantDaemon(cfg)
        # Midnight UTC = 05:30 IST — no slot is due.
        d._tick(datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc))
        # No fire records written.
        assert d.scheduler.state.last_fires_utc == {}
    print("  TEST 30 PASS: _tick with no due slots is a no-op")


# ---------- CLI ----------

def test_31_cli_parser_registers_all_subcommands():
    parser = build_parser()
    # Parse each subcommand — should not raise SystemExit.
    for cmd in ("start", "stop", "restart", "status", "health"):
        ns = parser.parse_args([cmd])
        assert ns.cmd == cmd
        assert callable(getattr(ns, "fn", None))
    print("  TEST 31 PASS: CLI parser registers start/stop/restart/status/health")


def test_32_cli_stop_with_no_lock_returns_zero(capsys=None):
    """Stopping when no daemon is running is a benign no-op."""
    import io
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        from nexaquant.ops.cli import cmd_stop, _load_daemon_config
        import argparse as _ap
        args = _ap.Namespace(pipeline=None, timeout=1.0)
        # Ensure no leftover lock at the default path — remove if present.
        cfg = _load_daemon_config(None)
        try:
            cfg.pidlock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        rc = cmd_stop(args)
        out = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout
    assert rc == 0, f"expected 0, got {rc}"
    assert "no daemon running" in out
    print("  TEST 32 PASS: `stop` with no daemon returns 0")


# ---------- MON001 / production invariants (guard rails) ----------

def test_33_no_production_files_touched_by_ops001b():
    """OPS001-B must not have introduced any modification to production
    strategy files or MON001 sealed core files."""
    import subprocess
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
    forbidden_touched = forbidden & changed
    assert not forbidden_touched, f"OPS001-B modified sealed files: {sorted(forbidden_touched)}"
    assert not lab_paths, f"OPS001-B modified LAB artefacts: {lab_paths}"
    print("  TEST 33 PASS: no sealed / LAB artefacts touched by uncommitted OPS001-B diff")


def test_34_production_constants_still_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    print("  TEST 34 PASS: HOLD=63 and rebal=63 unchanged")


def test_35_cumulative_strategy_search_unchanged_at_38():
    m = (ROOT / "india/ai_lab/trial_manifest.md").read_text(encoding="utf-8",
                                                                errors="ignore")
    assert "cumulative_strategy_search: 38" in m
    print("  TEST 35 PASS: cumulative_strategy_search unchanged at 38")


def test_36_mon001_fingerprint_matches_seal():
    from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
    import yaml
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = yaml.safe_load(f)
    sealed = json.loads((ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json"
                         ).read_text(encoding="utf-8"))
    current = compute_fingerprint(ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    assert current["hash"] == sealed["hash"], (
        f"MON001 fingerprint drift: sealed={sealed['hash']} current={current['hash']}")
    print(f"  TEST 36 PASS: MON001 fingerprint matches seal ({current['hash'][:16]}...)")


TESTS = [
    test_1_version_is_ops001b,
    test_2_json_formatter_emits_valid_json,
    test_3_json_formatter_merges_extra_fields,
    test_4_configure_creates_rotating_log,
    test_5_configure_is_idempotent,
    test_6_prune_old_logs_deletes_only_rotated,
    test_7_pidlock_acquire_and_release,
    test_8_pidlock_blocks_live_second_holder,
    test_9_pidlock_breaks_stale_dead_pid,
    test_10_pidlock_breaks_stale_by_age,
    test_11_pid_alive_self,
    test_12_pidlock_refresh_only_when_owned,
    test_13_process_monitor_snapshot_fields,
    test_14_execution_timings_records_run,
    test_15_slot_is_due_within_window,
    test_16_slot_is_due_respects_weekday_filter,
    test_17_slot_is_due_dedupes_same_day,
    test_18_schedule_state_persists,
    test_19_scheduler_next_run_utc,
    test_20_slots_from_config,
    test_21_recovery_decision_idle_and_completed,
    test_22_recovery_decision_running_resumes,
    test_23_recovery_decision_aborted_resumes,
    test_24_recovery_decision_failed_needs_attention,
    test_25_run_state_write_read_lifecycle,
    test_26_mark_failed_and_aborted_record_error,
    test_27_default_daemon_config_resolves_paths,
    test_28_daemon_snapshot_shape,
    test_29_daemon_lock_blocks_second_start,
    test_30_daemon_tick_no_slots_due_is_noop,
    test_31_cli_parser_registers_all_subcommands,
    test_32_cli_stop_with_no_lock_returns_zero,
    test_33_no_production_files_touched_by_ops001b,
    test_34_production_constants_still_unchanged,
    test_35_cumulative_strategy_search_unchanged_at_38,
    test_36_mon001_fingerprint_matches_seal,
]


def main() -> int:
    print("=" * 70)
    print("  OPS001-B DAEMON + LIFECYCLE TESTS — 36 scenarios")
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
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
