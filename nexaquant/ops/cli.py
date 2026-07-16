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


# ---- OPS001-C notify subcommands -----------------------------------


def _notify_paths(cfg) -> dict[str, Path]:
    reports = cfg.repo_root / "reports"
    return {
        "alerts": reports / "ops_alerts.jsonl",
        "queue": reports / "ops_notify_queue.jsonl",
        "dlq": reports / "ops_notify_dlq.jsonl",
        "delivered": reports / "ops_notify_delivered.jsonl",
    }


def _build_all_channels():
    """Instantiate one of every configured channel type. Unconfigured
    channels are included but report configured=False."""
    from .notify.file import FileChannel
    from .notify.telegram import TelegramChannel
    from .notify.email import EmailChannel
    from .notify.slack import SlackChannel
    from .notify.discord import DiscordChannel
    from .notify.webhook import WebhookChannel
    return [
        FileChannel(Path("reports/ops_alerts.jsonl")),
        TelegramChannel(),
        EmailChannel(),
        SlackChannel(),
        DiscordChannel(),
        WebhookChannel(),
    ]


def cmd_notify_test(args: argparse.Namespace) -> int:
    """Emit a synthetic INFO/WARN/ERROR/CRITICAL notification to exercise
    the routing policy end-to-end. Does NOT actually contact remote
    services unless they are configured."""
    from .events import Severity
    from .notify.base import Notification
    from .notify.manager import NotificationManager
    from .notify.file import FileChannel

    cfg = _load_daemon_config(args.pipeline)
    paths = _notify_paths(cfg)
    channels = _build_all_channels()
    # Ensure FileChannel writes to the ACTUAL alerts path (the default in
    # _build_all_channels uses a relative path from the daemon's cwd).
    channels[0] = FileChannel(paths["alerts"])

    mgr = NotificationManager(channels=channels)
    sev = Severity(args.severity.upper() if args.severity else "INFO")
    note = Notification.new(severity=sev, source="cli.notify.test",
                              title=f"CLI test notification ({sev.value})",
                              body=args.message or "This is a test emitted by `notify test`.")
    results = mgr.emit(note)
    payload = {
        "severity": sev.value,
        "channels_attempted": [r.channel for r in results if r.accepted],
        "channels_skipped_by_severity": [r.channel for r in results if not r.accepted],
        "per_channel": [{"channel": r.channel, "ok": r.ok, "accepted": r.accepted}
                        for r in results],
    }
    _print_json(payload)
    return 0 if all(r.ok for r in results if r.accepted) else 1


def cmd_notify_status(args: argparse.Namespace) -> int:
    from .notify.health import notification_status, channel_health
    cfg = _load_daemon_config(args.pipeline)
    paths = _notify_paths(cfg)
    channels = _build_all_channels()
    payload = {
        "status": notification_status(alerts_jsonl=paths["alerts"],
                                        queue_path=paths["queue"],
                                        dlq_path=paths["dlq"],
                                        delivered_path=paths["delivered"]),
        "channel_health": channel_health(channels),
    }
    _print_json(payload)
    return 0


def cmd_notify_retry(args: argparse.Namespace) -> int:
    """Drain the retry queue. For each ready entry, look up the target
    channel and re-attempt delivery."""
    from .notify.retry_queue import RetryQueue, process_queue
    from .notify.file import FileChannel

    cfg = _load_daemon_config(args.pipeline)
    paths = _notify_paths(cfg)
    channels = _build_all_channels()
    channels[0] = FileChannel(paths["alerts"])
    ch_map = {c.name: c for c in channels}
    q = RetryQueue(queue_path=paths["queue"], dlq_path=paths["dlq"],
                     delivered_path=paths["delivered"])
    summary = process_queue(q, ch_map, max_dispatch=int(args.max_dispatch))
    _print_json({"retry_summary": summary, "queue_stats": q.stats()})
    return 0


def cmd_notify_history(args: argparse.Namespace) -> int:
    from .notify.history import HistoryFilter, load_history, to_csv, markdown_summary

    cfg = _load_daemon_config(args.pipeline)
    paths = _notify_paths(cfg)
    since = None
    if args.since_hours:
        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(hours=float(args.since_hours))
    flt = HistoryFilter(since_utc=since)
    rows = load_history(paths["alerts"], flt)
    fmt = (args.format or "json").lower()
    if fmt == "csv":
        print(to_csv(rows), end="")
    elif fmt == "markdown":
        print(markdown_summary(rows,
                                 title=f"Notification history "
                                       f"({len(rows)} events)"), end="")
    else:
        _print_json({"count": len(rows), "rows": rows[-500:]})
    return 0


def cmd_notify_purge(args: argparse.Namespace) -> int:
    """Purge delivered ledger and DLQ. Interactive by default; --yes to skip."""
    from .notify.retry_queue import RetryQueue

    cfg = _load_daemon_config(args.pipeline)
    paths = _notify_paths(cfg)
    q = RetryQueue(queue_path=paths["queue"], dlq_path=paths["dlq"],
                     delivered_path=paths["delivered"])
    if not args.yes:
        stats = q.stats()
        print("This will purge the delivered ledger and DLQ. Current counts:")
        _print_json(stats)
        print("Re-run with --yes to confirm.")
        return 2
    d = q.purge_delivered()
    x = q.purge_dlq()
    _print_json({"delivered_purged": d, "dlq_purged": x})
    return 0


# ---- dispatcher ------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nexaquant-ops",
        description="NexaQuant operations daemon (OPS001-B/-C).")
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

    # OPS001-C: notify subcommands.
    notify_p = sub.add_parser("notify", help="Notification subsystem controls")
    notify_sub = notify_p.add_subparsers(dest="notify_cmd", required=True)

    test_p = notify_sub.add_parser("test", help="Emit a synthetic notification")
    test_p.add_argument("--severity", type=str, default="INFO",
                         choices=["INFO", "WARN", "ERROR", "CRITICAL", "info", "warn", "error", "critical"])
    test_p.add_argument("--message", type=str, default="",
                         help="Optional body text; default is a canned message.")
    test_p.set_defaults(fn=cmd_notify_test)

    notify_sub.add_parser("status",
                             help="Print notification subsystem status + per-channel health").set_defaults(fn=cmd_notify_status)

    retry_p = notify_sub.add_parser("retry", help="Drain the retry queue once")
    retry_p.add_argument("--max-dispatch", type=int, default=50,
                          help="Maximum ready entries to process in one call.")
    retry_p.set_defaults(fn=cmd_notify_retry)

    hist_p = notify_sub.add_parser("history", help="Print alert history")
    hist_p.add_argument("--format", type=str, default="json",
                         choices=["json", "csv", "markdown"])
    hist_p.add_argument("--since-hours", type=float, default=None,
                         help="Filter to events from the last N hours.")
    hist_p.set_defaults(fn=cmd_notify_history)

    purge_p = notify_sub.add_parser("purge",
                                       help="Purge delivered ledger and DLQ")
    purge_p.add_argument("--yes", action="store_true",
                           help="Skip confirmation prompt.")
    purge_p.set_defaults(fn=cmd_notify_purge)

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
