"""FileChannel — always-succeeds fallback that appends to a JSONL file.

Every operational alert MUST end up in this channel's log even if all other
channels fail. Used as the "of last resort" delivery target so no notification
is ever silently lost.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..events import Severity
from .base import Notification, NotificationChannel


class FileChannel(NotificationChannel):
    """Append every notification to a JSONL file. Never raises."""

    def __init__(self, path: Path | str, min_severity: Severity = Severity.INFO):
        self.path = Path(path)
        self._min_severity = min_severity
        # Ensure parent exists — no I/O at construction time on write to catch
        # the ONE case where the disk is full or the path is invalid.
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Deferred to send() where it can be reported without raising.
            pass

    @property
    def name(self) -> str:
        return "file"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    def send(self, notification: Notification) -> bool:
        if not self.accepts(notification.severity):
            return True   # filtered by severity is not a failure
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(notification.as_dict(), ensure_ascii=False,
                                    default=str) + "\n")
            return True
        except Exception:
            # Best-effort. If the FILE channel fails, something is very wrong
            # (disk full, permission), but we still must not raise.
            return False
