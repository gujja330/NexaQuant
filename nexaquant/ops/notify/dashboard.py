"""OPS001-C · Notification dashboard.

Reads on-disk state (alerts, retry queue, DLQ, delivered ledger) and produces
a single JSON snapshot summarising:

- pending retries (per channel)
- delivered successfully-after-retry (24h + all-time)
- dead-letter entries (per channel)
- retry counts per channel
- last-success / last-failure timestamps per channel

This is a *view*, not a mutation. Safe to call from CLI or from a periodic
observer.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_dashboard(*,
                    alerts_jsonl: Path,
                    queue_path: Path,
                    dlq_path: Path,
                    delivered_path: Path,
                    channel_names: list[str] | None = None) -> dict:
    """Return the dashboard snapshot dict."""
    alerts = _read_jsonl(alerts_jsonl)
    pending = _read_jsonl(queue_path)
    dlq = _read_jsonl(dlq_path)
    delivered = _read_jsonl(delivered_path)

    pending_per_channel: Counter = Counter(e.get("channel", "?") for e in pending)
    dlq_per_channel: Counter = Counter(e.get("channel", "?") for e in dlq)
    delivered_per_channel: Counter = Counter(e.get("channel", "?") for e in delivered)

    retry_counts: dict[str, int] = defaultdict(int)
    for e in pending + dlq + delivered:
        retry_counts[e.get("channel", "?")] += int(e.get("attempts", 0))

    # Last-success (from delivered) / last-failure (from dlq) per channel.
    last_success: dict[str, str] = {}
    for e in delivered:
        ch = e.get("channel", "?")
        ts = e.get("delivered_at_utc", "") or e.get("enqueued_at_utc", "")
        if ts and (ch not in last_success or ts > last_success[ch]):
            last_success[ch] = ts
    last_failure: dict[str, str] = {}
    for e in dlq:
        ch = e.get("channel", "?")
        ts = e.get("moved_to_dlq_at_utc", "") or e.get("enqueued_at_utc", "")
        if ts and (ch not in last_failure or ts > last_failure[ch]):
            last_failure[ch] = ts

    channels = channel_names or sorted(
        set(pending_per_channel) | set(dlq_per_channel) | set(delivered_per_channel))

    per_channel_rows = []
    for name in channels:
        per_channel_rows.append({
            "channel": name,
            "pending": int(pending_per_channel.get(name, 0)),
            "delivered": int(delivered_per_channel.get(name, 0)),
            "failed_to_dlq": int(dlq_per_channel.get(name, 0)),
            "total_retry_attempts": int(retry_counts.get(name, 0)),
            "last_success_utc": last_success.get(name, ""),
            "last_failure_utc": last_failure.get(name, ""),
        })

    alerts_by_sev = Counter(a.get("severity", "") for a in alerts)

    return {
        "generated_at_utc": _iso_utc(),
        "totals": {
            "alerts_recorded": len(alerts),
            "pending_retries": len(pending),
            "delivered_via_retry": len(delivered),
            "dead_letter": len(dlq),
        },
        "alerts_by_severity": {sev: int(alerts_by_sev.get(sev, 0))
                                for sev in ("INFO", "WARN", "ERROR", "CRITICAL")},
        "per_channel": per_channel_rows,
    }


def dashboard_markdown(snapshot: dict) -> str:
    """Render the dashboard dict as a compact markdown summary."""
    lines = ["# NexaQuant · Notification Dashboard", ""]
    lines.append(f"**Generated:** {snapshot.get('generated_at_utc', '')}")
    lines.append("")
    tot = snapshot.get("totals", {})
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- Alerts recorded: **{tot.get('alerts_recorded', 0)}**")
    lines.append(f"- Pending retries: **{tot.get('pending_retries', 0)}**")
    lines.append(f"- Delivered via retry: **{tot.get('delivered_via_retry', 0)}**")
    lines.append(f"- Dead-letter entries: **{tot.get('dead_letter', 0)}**")
    lines.append("")
    lines.append("## Alerts by severity")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in ("INFO", "WARN", "ERROR", "CRITICAL"):
        lines.append(f"| {sev} | {snapshot.get('alerts_by_severity', {}).get(sev, 0)} |")
    lines.append("")
    lines.append("## Per-channel status")
    lines.append("")
    lines.append("| Channel | Pending | Delivered | DLQ | Retry attempts | Last success | Last failure |")
    lines.append("|---|---:|---:|---:|---:|---|---|")
    for row in snapshot.get("per_channel", []):
        lines.append(
            f"| `{row['channel']}` "
            f"| {row['pending']} "
            f"| {row['delivered']} "
            f"| {row['failed_to_dlq']} "
            f"| {row['total_retry_attempts']} "
            f"| {row['last_success_utc'] or '—'} "
            f"| {row['last_failure_utc'] or '—'} |")
    lines.append("")
    return "\n".join(lines) + "\n"


__all__ = [
    "build_dashboard",
    "dashboard_markdown",
]
