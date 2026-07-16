"""OPS001-C · Slack notification channel (Incoming Webhooks).

Reads webhook URL from environment:
  NEXAQUANT_SLACK_WEBHOOK_URL — https://hooks.slack.com/services/T.../B.../...
  NEXAQUANT_SLACK_MIN_SEVERITY — optional override (INFO/WARN/ERROR/CRITICAL)

When the URL is absent, `configured` is False and `send()` returns False
without contacting the network.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..events import Severity
from .base import Notification, NotificationChannel


_SEVERITY_ICON = {
    "INFO": ":information_source:",
    "WARN": ":warning:",
    "ERROR": ":no_entry:",
    "CRITICAL": ":rotating_light:",
}


class SlackChannel(NotificationChannel):
    def __init__(self, min_severity: Severity = Severity.ERROR,
                  timeout_s: float = 15.0):
        self._min_severity = min_severity
        self.timeout_s = float(timeout_s)
        self.webhook_url = os.environ.get("NEXAQUANT_SLACK_WEBHOOK_URL", "").strip()

    @property
    def name(self) -> str:
        return "slack"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    @property
    def configured(self) -> bool:
        return self.webhook_url.startswith("https://hooks.slack.com/")

    def _payload(self, note: Notification) -> dict:
        sev = note.severity.value if hasattr(note.severity, "value") else str(note.severity)
        icon = _SEVERITY_ICON.get(sev, "")
        lines = [f"{icon} *NexaQuant {sev}* — {note.title}",
                 f"_source_: `{note.source}` · _time_: `{note.timestamp_utc}`"]
        if note.body:
            body = note.body[:2500]  # Slack text blocks cap ~3k safely
            lines.append(f"```{body}```")
        if note.context:
            fields = "\n".join(f"• *{k}*: `{v}`" for k, v in sorted(note.context.items()))
            lines.append(fields)
        return {"text": "\n".join(lines)}

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            return False
        try:
            data = json.dumps(self._payload(notification)).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url, data=data,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            # Slack returns 400 with "invalid_payload" — treat as failure.
            return 200 <= e.code < 300
        except Exception:
            return False


__all__ = ["SlackChannel"]
