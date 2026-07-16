"""OPS001-C · Notification health APIs.

Callable functions the CLI and daemon use to probe the notification
subsystem. All three return dicts safe to serialize into `ops_status.json`
or dump to stdout.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dashboard import build_dashboard
from .base import Notification, NotificationChannel


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def notification_status(*,
                         alerts_jsonl: Path,
                         queue_path: Path,
                         dlq_path: Path,
                         delivered_path: Path,
                         channel_names: list[str] | None = None) -> dict:
    """High-level status: OK / DEGRADED / FAILED plus counts.

    Rules:
    - `dead_letter > 0` → DEGRADED
    - Every configured channel with 0 deliveries AND 0 pending after 24h
      operation → DEGRADED (nothing coming through — likely misconfigured)
    - Otherwise → OK
    """
    snap = build_dashboard(alerts_jsonl=alerts_jsonl,
                            queue_path=queue_path,
                            dlq_path=dlq_path,
                            delivered_path=delivered_path,
                            channel_names=channel_names)
    dl = snap["totals"]["dead_letter"]
    status = "DEGRADED" if dl > 0 else "OK"
    return {
        "generated_at_utc": _iso_utc(),
        "status": status,
        "totals": snap["totals"],
        "alerts_by_severity": snap["alerts_by_severity"],
        "per_channel": snap["per_channel"],
    }


def delivery_metrics(*,
                      alerts_jsonl: Path,
                      queue_path: Path,
                      dlq_path: Path,
                      delivered_path: Path,
                      window_hours: int = 24) -> dict:
    """Delivery metrics for the last `window_hours`."""
    from .history import HistoryFilter, load_history
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    recent_alerts = load_history(alerts_jsonl,
                                   HistoryFilter(since_utc=since, until_utc=now))
    sev_ct = Counter(r.get("severity", "") for r in recent_alerts)
    snap = build_dashboard(alerts_jsonl=alerts_jsonl,
                            queue_path=queue_path,
                            dlq_path=dlq_path,
                            delivered_path=delivered_path)
    return {
        "generated_at_utc": _iso_utc(),
        "window_hours": int(window_hours),
        "alerts_in_window": len(recent_alerts),
        "alerts_by_severity_in_window": {
            "INFO": int(sev_ct.get("INFO", 0)),
            "WARN": int(sev_ct.get("WARN", 0)),
            "ERROR": int(sev_ct.get("ERROR", 0)),
            "CRITICAL": int(sev_ct.get("CRITICAL", 0)),
        },
        "totals_all_time": snap["totals"],
    }


def channel_health(channels: list[NotificationChannel]) -> dict:
    """Enumerate configured channels: is each wired up? What min-severity
    filter does each apply? Never sends a probe message."""
    rows = []
    for ch in channels:
        configured = True
        # Prefer explicit `configured` attribute where present.
        if hasattr(ch, "configured"):
            try:
                configured = bool(ch.configured)
            except Exception:
                configured = False
        min_sev = ch.min_severity
        if hasattr(min_sev, "value"):
            min_sev_value = min_sev.value
        else:
            min_sev_value = str(min_sev)
        rows.append({
            "name": ch.name,
            "configured": bool(configured),
            "min_severity": min_sev_value,
            "class": type(ch).__name__,
        })
    return {
        "generated_at_utc": _iso_utc(),
        "channels": rows,
        "channels_total": len(rows),
        "channels_configured": sum(1 for r in rows if r["configured"]),
    }


__all__ = [
    "notification_status",
    "delivery_metrics",
    "channel_health",
]
