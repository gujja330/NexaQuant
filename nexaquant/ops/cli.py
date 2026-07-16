"""OPS001-B CLI dispatcher for the daemon.

Subcommands:
  start     Foreground daemon (systemd / Task Scheduler / launchd will invoke this)
  stop      Signal a running daemon to shut down
  restart   stop; wait; start
  status    Print current lock holder + last runs + next scheduled fire
  health    Run one MON001 health-check pass and print its report + exit code

Never mutates production files. Never touches MON001 sealed files.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__ as _ops_version
from .daemon import DaemonConfig, NexaQuantDaemon, default_daemon_config
from .pidlock import PidLock
from .scheduler import Scheduler


DEFAULT_STOP_TIMEOUT_S = 30.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_daemon_config(pipeline: str | None) -> DaemonConfig:
    return default_daemon_config(repo_root=_repo_root(),
                                   pipeline_config=Path(pipeline) if pipeline else None)


def _print_json(obj: dict) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=True))


# ---- subcommands -----------------------------------------------------


def cmd_start(args: argparse.Namespace) -> int:
    cfg = _load_daemon_config(args.pipeline)
    daemon = NexaQuantDaemon(cfg)
    return daemon.start()


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = _load_daemon_config(args.pipeline)
    lock = PidLock(cfg.pidlock_path)
    holder = lock.read()
    if holder is None:
        print("no daemon running (lock file absent)")
        return 0
    if holder.pid == os.getpid():
        print(f"refusing to signal self (pid {os.getpid()})")
        return 2

    sig = signal.SIGTERM
    try:
        os.kill(holder.pid, sig)
    except ProcessLookupError:
        print(f"pid {holder.pid} not found — removing stale lock")
        try:
            cfg.pidlock_path.unlink(missing_ok=True)
        except OSError:
            pass
        return 0
    except PermissionError as e:
        print(f"permission denied signaling pid {holder.pid}: {e}")
        return 4

    deadline = time.time() + float(args.timeout)
    print(f"SIGTERM sent to pid {holder.pid}; waiting up to {args.timeout:.0f}s")
    while time.time() < deadline:
        try:
            os.kill(holder.pid, 0)
        except ProcessLookupError:
            print("daemon stopped.")
            return 0
        time.sleep(0.5)

    print(f"daemon still alive after {args.timeout:.0f}s — leaving lock in place")
    return 1


def cmd_restart(args: argparse.Namespace) -> int:
    rc = cmd_stop(args)
    if rc not in (0, 1):
        return rc
    time.sleep(1.0)
    return cmd_start(args)


def cmd_status(args: argparse.Namespace) -> int:
    cfg = _load_daemon_config(args.pipeline)
    lock = PidLock(cfg.pidlock_path)
    holder = lock.read()

    sched = Scheduler(cfg.slots, cfg.schedule_state_path)
    now = datetime.now(timezone.utc)
    next_run = sched.next_run_utc(now_utc=now)

    ops_status = {}
    try:
        ops_status = json.loads(cfg.service_config.status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    payload = {
        "ops_version": _ops_version,
        "daemon_running": holder is not None,
        "lock_holder": holder.as_dict() if holder else None,
        "slots": [
            {"name": s.name, "hour": s.hour, "minute": s.minute,
              "weekdays": list(s.weekdays),
              "tz_offset_hours": s.tz_offset_hours,
              "last_fired_utc": sched.state.last_fires_utc.get(s.name, "")}
            for s in cfg.slots
        ],
        "next_run_utc": next_run.isoformat(timespec="seconds") if next_run else "",
        "ops_status_snapshot": ops_status,
    }
    _print_json(payload)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Run the MON001 health check once. Delegates to the sealed module —
    does NOT change its semantics."""
    try:
        from india.monitoring.MON001_Forward_Validation.ops.health_check import (
            run_health_checks, format_report,
        )
    except Exception as e:
        print(f"failed to import MON001 health_check module: {e}")
        return 2
    report = run_health_checks()
    print(format_report(report))
    return int(report.exit_code)


# ---- dispatcher ------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nexaquant-ops",
        description="NexaQuant operations daemon (OPS001-B).")
    p.add_argument("--pipeline", type=str, default=None,
                    help="Path to pipeline YAML. Defaults to nexaquant/ops/pipelines/aegis_daily.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("start",   help="Start the daemon (foreground)").set_defaults(fn=cmd_start)
    stop_p = sub.add_parser("stop", help="Stop a running daemon")
    stop_p.add_argument("--timeout", type=float, default=DEFAULT_STOP_TIMEOUT_S,
                         help="Seconds to wait for graceful shutdown")
    stop_p.set_defaults(fn=cmd_stop)
    restart_p = sub.add_parser("restart", help="Stop then start")
    restart_p.add_argument("--timeout", type=float, default=DEFAULT_STOP_TIMEOUT_S)
    restart_p.set_defaults(fn=cmd_restart)
    sub.add_parser("status", help="Print daemon status as JSON").set_defaults(fn=cmd_status)
    sub.add_parser("health", help="Run MON001 health check once").set_defaults(fn=cmd_health)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.fn(args))


__all__ = [
    "DEFAULT_STOP_TIMEOUT_S",
    "build_parser",
    "cmd_start", "cmd_stop", "cmd_restart", "cmd_status", "cmd_health",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
