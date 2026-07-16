"""OPS001-C · Retry queue with exponential backoff + dead-letter queue.

Persistent JSONL queue for notifications whose delivery failed. A separate
processor (invoked either by the daemon tick or the `nexaquant-ops notify
retry` CLI) drains the queue on backoff schedule. After max_attempts,
entries move to the dead-letter queue (DLQ) — never silently dropped.

State layout (one file per queue):
  reports/ops_notify_queue.jsonl       — pending retries
  reports/ops_notify_dlq.jsonl         — dead-letter (max attempts exceeded)
  reports/ops_notify_delivered.jsonl   — successfully retried (audit trail)

Concurrency: single-writer assumption (the daemon owns these files). If a
second writer appears, entries can be lost — this is documented in the DESIGN.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from ..events import Severity
from .base import Notification


DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_INITIAL_BACKOFF_S = 30.0
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_BACKOFF_S = 1800.0    # 30 minutes cap


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_ts() -> float:
    return time.time()


@dataclass
class QueueEntry:
    """One notification awaiting delivery on one channel."""
    id: str
    notification: dict          # Notification.as_dict()
    channel: str                # name of the channel to retry against
    attempts: int = 0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S
    backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER
    max_backoff_s: float = DEFAULT_MAX_BACKOFF_S
    next_retry_ts: float = 0.0
    last_error: str = ""
    enqueued_at_utc: str = field(default_factory=_iso_utc)

    def as_dict(self) -> dict:
        return asdict(self)

    def backoff_for_attempt(self, attempt_idx: int) -> float:
        """Compute delay in seconds for the (0-indexed) attempt."""
        if attempt_idx <= 0:
            return 0.0
        raw = self.initial_backoff_s * (self.backoff_multiplier ** (attempt_idx - 1))
        return float(min(raw, self.max_backoff_s))

    def schedule_next(self, err: str = "") -> None:
        self.attempts += 1
        self.last_error = str(err)[:1024]
        self.next_retry_ts = _now_ts() + self.backoff_for_attempt(self.attempts)


def _atomic_append(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)


class RetryQueue:
    """Persistent notification retry queue with DLQ."""

    def __init__(self,
                  queue_path: Path,
                  dlq_path: Path,
                  delivered_path: Path):
        self.queue_path = Path(queue_path)
        self.dlq_path = Path(dlq_path)
        self.delivered_path = Path(delivered_path)

    # -- enqueue / drain -------------------------------------------------

    def enqueue(self, notification: Notification, channel: str,
                 max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                 initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
                 last_error: str = "") -> QueueEntry:
        entry_id = f"{notification.timestamp_utc}::{channel}::{abs(hash(notification.title)) % 1_000_000:06d}"
        entry = QueueEntry(
            id=entry_id,
            notification=notification.as_dict(),
            channel=channel,
            attempts=0,
            max_attempts=max_attempts,
            initial_backoff_s=initial_backoff_s,
        )
        # First retry is scheduled immediately (attempts=0 -> backoff 0).
        entry.next_retry_ts = _now_ts() + entry.backoff_for_attempt(1)
        entry.last_error = str(last_error)[:1024]
        _atomic_append(self.queue_path, entry.as_dict())
        return entry

    def _pending(self) -> list[QueueEntry]:
        rows = _read_jsonl(self.queue_path)
        entries: list[QueueEntry] = []
        allowed = set(QueueEntry.__dataclass_fields__.keys())
        for r in rows:
            try:
                entries.append(QueueEntry(**{k: v for k, v in r.items() if k in allowed}))
            except (TypeError, ValueError):
                continue
        return entries

    def pending(self) -> list[QueueEntry]:
        return self._pending()

    def ready(self, now_ts: float | None = None) -> list[QueueEntry]:
        """Return every queued entry whose next_retry_ts <= now."""
        ts = now_ts if now_ts is not None else _now_ts()
        return [e for e in self._pending() if e.next_retry_ts <= ts]

    def mark_delivered(self, entry_id: str) -> bool:
        rows = _read_jsonl(self.queue_path)
        remaining: list[dict] = []
        matched: dict | None = None
        for r in rows:
            if r.get("id") == entry_id and matched is None:
                matched = r
            else:
                remaining.append(r)
        if matched is None:
            return False
        _write_jsonl(self.queue_path, remaining)
        matched = dict(matched)
        matched["delivered_at_utc"] = _iso_utc()
        _atomic_append(self.delivered_path, matched)
        return True

    def mark_failed(self, entry_id: str, err: str) -> tuple[bool, bool]:
        """Update attempt count / next_retry OR move to DLQ.

        Returns (found, moved_to_dlq)."""
        rows = _read_jsonl(self.queue_path)
        found = False
        moved_to_dlq = False
        updated: list[dict] = []
        for r in rows:
            if r.get("id") != entry_id or found:
                updated.append(r)
                continue
            found = True
            entry = QueueEntry(**{k: r.get(k) for k in QueueEntry.__dataclass_fields__
                                   if k in r})
            entry.schedule_next(err=err)
            if entry.attempts >= entry.max_attempts:
                moved_to_dlq = True
                dlq_row = entry.as_dict()
                dlq_row["moved_to_dlq_at_utc"] = _iso_utc()
                _atomic_append(self.dlq_path, dlq_row)
            else:
                updated.append(entry.as_dict())
        if found:
            _write_jsonl(self.queue_path, updated)
        return found, moved_to_dlq

    # -- inspection ------------------------------------------------------

    def stats(self) -> dict:
        pending = _read_jsonl(self.queue_path)
        dlq = _read_jsonl(self.dlq_path)
        delivered = _read_jsonl(self.delivered_path)
        return {
            "pending": len(pending),
            "dlq": len(dlq),
            "delivered": len(delivered),
            "queue_path": str(self.queue_path),
            "dlq_path": str(self.dlq_path),
            "delivered_path": str(self.delivered_path),
        }

    def purge_delivered(self) -> int:
        rows = _read_jsonl(self.delivered_path)
        _write_jsonl(self.delivered_path, [])
        return len(rows)

    def purge_dlq(self) -> int:
        rows = _read_jsonl(self.dlq_path)
        _write_jsonl(self.dlq_path, [])
        return len(rows)


def process_queue(queue: RetryQueue,
                   channels: dict,   # {name: NotificationChannel}
                   now_ts: float | None = None,
                   max_dispatch: int = 50) -> dict:
    """Drain up to `max_dispatch` ready entries. For each, look up the channel
    and try `send()`. On success, mark delivered; on failure, `mark_failed()`
    which either re-schedules or moves to DLQ.

    Returns a summary dict."""
    ready = queue.ready(now_ts=now_ts)[:max_dispatch]
    delivered = 0
    reattempted = 0
    to_dlq = 0
    unroutable = 0
    for entry in ready:
        ch = channels.get(entry.channel)
        if ch is None:
            unroutable += 1
            queue.mark_failed(entry.id, err=f"channel '{entry.channel}' not available")
            continue
        # Re-materialize the Notification from the persisted dict.
        note = Notification(
            timestamp_utc=entry.notification.get("timestamp_utc", _iso_utc()),
            severity=Severity(entry.notification.get("severity", "INFO")),
            source=entry.notification.get("source", ""),
            title=entry.notification.get("title", ""),
            body=entry.notification.get("body", ""),
            context=entry.notification.get("context", {}) or {},
        )
        try:
            ok = bool(ch.send(note))
        except Exception as e:
            queue.mark_failed(entry.id, err=f"{type(e).__name__}: {e}")
            ok = False
        if ok:
            queue.mark_delivered(entry.id)
            delivered += 1
        else:
            found, moved = queue.mark_failed(entry.id, err="send returned False")
            if moved:
                to_dlq += 1
            else:
                reattempted += 1
    return {
        "attempted": len(ready), "delivered": delivered,
        "reattempted": reattempted, "moved_to_dlq": to_dlq,
        "unroutable": unroutable,
    }


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_INITIAL_BACKOFF_S",
    "DEFAULT_BACKOFF_MULTIPLIER",
    "DEFAULT_MAX_BACKOFF_S",
    "QueueEntry",
    "RetryQueue",
    "process_queue",
]
