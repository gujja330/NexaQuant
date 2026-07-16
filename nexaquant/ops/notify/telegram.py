"""TelegramChannel — operational alerts via the Telegram Bot API.

IMPORTANT: This channel is NOT for the daily recommendation message. The daily
message is generated + sent by `india/telegram_notify.py` (untouched, per the
OPS001-A contract). This channel is for OPS-layer alerts only — e.g.
"pipeline stage X failed after 3 retries".

Uses the same TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars but posts short
text messages via urllib (stdlib, no extra deps). Independent of the daily
notifier so a bug in one doesn't take down the other.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from ..events import Severity
from .base import Notification, NotificationChannel


TIMEOUT_S = 15.0
MAX_TEXT_LEN = 4000       # Telegram cap is 4096; leave headroom for wrapping


SEVERITY_PREFIX = {
    Severity.INFO: "ℹ️",
    Severity.WARN: "⚠️",
    Severity.CRITICAL: "🚨",
}


class TelegramChannel(NotificationChannel):
    """Deliver ops alerts to Telegram. Never raises."""

    def __init__(self, token: str | None = None, chat_id: str | None = None,
                 min_severity: Severity = Severity.WARN):
        # Allow env-driven config (CI mode) or explicit params (tests)
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "") or None
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "") or None
        self._min_severity = min_severity

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, notification: Notification) -> bool:
        if not self.accepts(notification.severity):
            return True
        if not self.configured:
            return False
        try:
            text = self._format(notification)
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self._chat_id,
                "text": text[:MAX_TEXT_LEN],
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }).encode()
            with urllib.request.urlopen(url, data=data, timeout=TIMEOUT_S) as resp:
                body = json.loads(resp.read())
            return bool(body.get("ok"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                OSError, json.JSONDecodeError):
            return False
        except Exception:
            # Belt-and-suspenders — a channel must NEVER propagate.
            return False

    @staticmethod
    def _format(n: Notification) -> str:
        icon = SEVERITY_PREFIX.get(
            Severity(n.severity) if not isinstance(n.severity, Severity) else n.severity,
            "•")
        lines = [f"{icon} <b>[{n.severity.value if isinstance(n.severity, Severity) else n.severity}]</b> "
                  f"{n.title}"]
        if n.source:
            lines.append(f"<i>source:</i> <code>{n.source}</code>")
        if n.body:
            lines.append("")
            lines.append(n.body)
        return "\n".join(lines)
