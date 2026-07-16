"""OPS001-B NexaQuant daemon.

A long-lived process that:
- Acquires a PID lock so only one daemon runs per host
- Polls a slot-based schedule every N seconds
- Invokes NexaQuantService.run_once() when a slot is due
- Records interrupted-pipeline recovery state
- Emits structured JSON logs and rotating log files
- Reports uptime / memory / CPU into ops_status.json.metadata
- Handles SIGTERM / SIGINT gracefully — completes current stage, then exits

Not a self-daemonizer. Expects to be launched under systemd (Linux) or Task
Scheduler (Windows) or launchd (macOS) — those handle restart-on-failure.

Design goals:
- No production strategy behaviour change
- Never touches MON001 sealed files
- Additive over OPS001-A — reuses NexaQuantService.run_once() verbatim
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__ as _ops_version
from .logging_setup import LogConfig, configure as configure_logging, get_logger, prune_old_logs
from .monitoring import ExecutionTimings, ProcessMonitor
from .pidlock import PidLock
from .recovery import (
    RecoveryAction, decide as decide_recovery,
    mark_aborted, mark_completed, mark_failed, mark_running, mark_starting,
    RunState,
)
from .scheduler import Scheduler, Slot, slots_from_config
from .service import NexaQuantService, default_config, ServiceConfig


DEFAULT_POLL_INTERVAL_S = 30.0
DEFAULT_LOCK_REFRESH_S = 900.0    # rewrite lock file every 15 min so stale-age check doesn't trip
DEFAULT_LOG_RETENTION_DAYS = 30


@dataclass
class DaemonConfig:
    """All the wiring the daemon needs. Every path defaults to the repo layout."""
    repo_root: Path
    service_config: ServiceConfig
    slots: list[Slot]
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    lock_refresh_s: float = DEFAULT_LOCK_REFRESH_S
    pidlock_path: Path = None                       # type: ignore[assignment]
    schedule_state_path: Path = None                # type: ignore[assignment]
    run_state_path: Path = None                     # type: ignore[assignment]
    log_dir: Path = None                            # type: ignore[assignment]
    log_retention_days: int = DEFAULT_LOG_RETENTION_DAYS
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 14
    stderr_mirror: bool = True

    def resolve_defaults(self) -> None:
        reports = self.repo_root / "reports"
        if self.pidlock_path is None:
            self.pidlock_path = reports / "ops_daemon.lock"
        if self.schedule_state_path is None:
            self.schedule_state_path = reports / "ops_schedule_state.json"
        if self.run_state_path is None:
            self.run_state_path = reports / "ops_run_state.json"
        if self.log_dir is None:
            self.log_dir = reports / "logs"


def default_daemon_config(repo_root: Path, pipeline_config: Path | None = None,
                           slots: list[Slot] | None = None) -> DaemonConfig:
    """Sensible defaults for a production install. Slots default to the same
    IST windows the GitHub-Actions cron uses (16:15 / 18:30 / 21:00 Mon-Fri)."""
    if slots is None:
        slots = [
            Slot(name="primary_1615_ist", hour=16, minute=15),
            Slot(name="backup_1830_ist", hour=18, minute=30),
            Slot(name="backup_2100_ist", hour=21, minute=0),
        ]
    cfg = DaemonConfig(
        repo_root=Path(repo_root).resolve(),
        service_config=default_config(repo_root=repo_root,
                                        pipeline_config=pipeline_config),
        slots=slots,
    )
    cfg.resolve_defaults()
    return cfg


class NexaQuantDaemon:
    """The daemon lifecycle. One instance per process."""

    def __init__(self, config: DaemonConfig):
        self.config = config
        self.config.resolve_defaults()
        self._start_ts = time.time()
        self._stop_event = threading.Event()
        self._current_slot: str = ""

        # Wiring: logger + lock + monitor + scheduler
        self.logger = configure_logging(LogConfig(
            log_dir=config.log_dir,
            max_bytes=config.log_max_bytes,
            backup_count=config.log_backup_count,
            stderr_mirror=config.stderr_mirror,
        ))
        self.lock = PidLock(config.pidlock_path)
        self.monitor = ProcessMonitor()
        self.scheduler = Scheduler(config.slots, config.schedule_state_path)
        self.timings = ExecutionTimings()
        self._last_lock_refresh_ts = 0.0

    # --- lifecycle -----------------------------------------------------

    def _install_signal_handlers(self) -> None:
        """Cross-platform graceful-shutdown wiring."""

        def _handler(signum, frame):
            self.logger.info(f"signal_received signum={signum} — initiating graceful shutdown",
                              extra={"signum": int(signum), "event": "shutdown_signal"})
            self._stop_event.set()

        # SIGTERM on both platforms; SIGINT (Ctrl-C) on both; SIGBREAK on Windows.
        try:
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, OSError):
            pass
        try:
            signal.signal(signal.SIGINT, _handler)
        except (ValueError, OSError):
            pass
        if hasattr(signal, "SIGBREAK"):
            try:
                signal.signal(signal.SIGBREAK, _handler)  # type: ignore[attr-defined]
            except (ValueError, OSError):
                pass

    def _handle_recovery(self) -> None:
        """Inspect leftover run_state and act on it."""
        prev = RunState.load(self.config.run_state_path)
        decision = decide_recovery(prev)
        if decision.action == RecoveryAction.NONE:
            return
        self.logger.warning(
            "recovery_decision",
            extra={
                "event": "recovery_decision",
                "action": decision.action.value,
                "reason": decision.reason,
                "previous_phase": decision.previous_phase,
                "previous_stage": decision.previous_stage,
                "started_at_utc": decision.started_at_utc,
                "slot_name": decision.slot_name,
            })
        # Clear stale run_state so the daemon starts clean.
        try:
            self.config.run_state_path.unlink(missing_ok=True)
        except OSError:
            pass

    def start(self) -> int:
        """Enter the daemon loop. Returns process exit code."""
        self._install_signal_handlers()
        if not self.lock.acquire():
            holder = self.lock.read()
            self.logger.error(
                "pid_lock_held — another daemon is already running",
                extra={"event": "startup_blocked",
                        "holder_pid": holder.pid if holder else -1,
                        "holder_host": holder.host if holder else ""})
            return 3
        try:
            self.logger.info(
                "daemon_started",
                extra={"event": "daemon_started",
                        "ops_version": _ops_version,
                        "pid": os.getpid(),
                        "slots": [s.name for s in self.config.slots],
                        "poll_interval_s": self.config.poll_interval_s})
            self._handle_recovery()
            return self._loop()
        finally:
            self.lock.release()
            self.logger.info("daemon_exited",
                              extra={"event": "daemon_exited",
                                      "uptime_s": round(self.monitor.uptime_s, 3)})

    def _loop(self) -> int:
        """Main polling loop. Exits when _stop_event is set."""
        while not self._stop_event.is_set():
            try:
                self._tick(datetime.now(timezone.utc))
            except Exception:
                self.logger.error(
                    "tick_exception",
                    extra={"event": "tick_exception",
                            "traceback": traceback.format_exc()})
            # Interruptible sleep so SIGTERM/SIGINT wake us within seconds.
            self._stop_event.wait(timeout=self.config.poll_interval_s)
        # If a pipeline was running when SIGTERM arrived, mark_aborted so the
        # NEXT daemon start emits a WARN-level recovery event.
        rs = RunState.load(self.config.run_state_path)
        if rs.phase in ("starting", "running"):
            mark_aborted(self.config.run_state_path,
                          reason="daemon received shutdown signal mid-pipeline")
        return 0

    def _tick(self, now_utc: datetime) -> None:
        """One poll iteration."""
        # Lock-file heartbeat so age-based stale detection never trips a
        # long-running daemon.
        if time.time() - self._last_lock_refresh_ts >= self.config.lock_refresh_s:
            self.lock.refresh()
            self._last_lock_refresh_ts = time.time()

        due = self.scheduler.due(now_utc=now_utc)
        if not due:
            return
        for slot in due:
            if self._stop_event.is_set():
                return
            self._fire_slot(slot)

    # --- pipeline execution --------------------------------------------

    def _fire_slot(self, slot: Slot) -> None:
        self._current_slot = slot.name
        self.logger.info("slot_firing", extra={"event": "slot_firing",
                                                 "slot": slot.name})
        run_state_path = self.config.run_state_path
        start_ts = time.time()
        try:
            mark_starting(run_state_path,
                           pipeline_name=str(self.config.service_config.pipeline_config.stem),
                           slot_name=slot.name, pid=os.getpid())
            mark_running(run_state_path, current_stage="<framework>")
            svc = NexaQuantService(self.config.service_config)
            rc = svc.run_once()
            duration = time.time() - start_ts
            if rc == 0:
                self.logger.info(
                    "slot_completed",
                    extra={"event": "slot_completed", "slot": slot.name,
                            "duration_s": round(duration, 3), "exit_code": rc})
                mark_completed(run_state_path)
            else:
                self.logger.error(
                    "slot_pipeline_failure",
                    extra={"event": "slot_pipeline_failure", "slot": slot.name,
                            "duration_s": round(duration, 3), "exit_code": rc})
                mark_failed(run_state_path, err=f"pipeline exit code {rc}")
            self.timings.record_run(
                duration_s=duration,
                per_stage_seconds=self._read_last_stage_seconds(),
                retries=0, failures=0 if rc == 0 else 1)
            # Only mark_fired when we didn't hit a framework crash.
            # Failed pipelines still count as "fired for today" — otherwise
            # the daemon would hammer the same slot repeatedly in a broken state.
            self.scheduler.mark_fired(slot.name, at_utc=datetime.now(timezone.utc))
        except Exception:
            tb = traceback.format_exc()
            self.logger.error("slot_framework_error",
                               extra={"event": "slot_framework_error",
                                       "slot": slot.name, "traceback": tb})
            mark_failed(run_state_path, err=tb.splitlines()[-1] if tb else "unknown")
        finally:
            self._current_slot = ""
            # Retention: prune old log rotations after every fire.
            try:
                prune_old_logs(self.config.log_dir, "nexaquant_ops.jsonl",
                               self.config.log_retention_days)
            except Exception:
                pass

    def _read_last_stage_seconds(self) -> dict[str, float]:
        """Best-effort read from ops_status.json's most recent write."""
        try:
            data = json.loads(self.config.service_config.status_path.read_text(
                encoding="utf-8"))
            return {}   # OPS001-A doesn't expose per-stage timing directly; OPS001-C will.
        except Exception:
            return {}

    # --- inspection ----------------------------------------------------

    def snapshot(self) -> dict:
        """A live view of daemon state — used by the CLI `status` subcommand."""
        proc = self.monitor.snapshot()
        return {
            "ops_version": _ops_version,
            "pid": os.getpid(),
            "uptime_s": round(self.monitor.uptime_s, 3),
            "current_slot": self._current_slot,
            "process": proc.as_dict(),
            "timings": self.timings.as_dict(),
            "slots": [s.name for s in self.config.slots],
            "last_fires_utc": self.scheduler.state.last_fires_utc,
            "next_run_utc": self._next_run_iso(),
        }

    def _next_run_iso(self) -> str:
        nxt = self.scheduler.next_run_utc()
        if nxt is None:
            return ""
        return nxt.astimezone(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "DEFAULT_POLL_INTERVAL_S",
    "DEFAULT_LOCK_REFRESH_S",
    "DEFAULT_LOG_RETENTION_DAYS",
    "DaemonConfig",
    "default_daemon_config",
    "NexaQuantDaemon",
]
