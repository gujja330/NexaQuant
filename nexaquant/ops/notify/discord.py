"""OPS001-C · Discord notification channel (webhook).

Reads webhook URL from environment:
  NEXAQUANT_DISCORD_WEBHOOK_URL — https://discord.com/api/webhooks/.../....

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


# Discord embed color-coding (decimal ints for the 24-bit RGB space).
_SEVERITY_COLOR = {
    "INFO": 0x3498DB,      # blue
    "WARN": 0xF1C40F,      # yellow
    "ERROR": 0xE67E22,     # orange
    "CRITICAL": 0xE74C3C,  # red
}


class DiscordChannel(NotificationChannel):
    def __init__(self, min_severity: Severity = Severity.ERROR,
                  timeout_s: float = 15.0):
        self._min_severity = min_severity
        self.timeout_s = float(timeout_s)
        self.webhook_url = os.environ.get("NEXAQUANT_DISCORD_WEBHOOK_URL", "").strip()

    @property
    def name(self) -> str:
        return "discord"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    @property
    def configured(self) -> bool:
        return self.webhook_url.startswith("https://discord.com/api/webhooks/") or \
               self.webhook_url.startswith("https://discordapp.com/api/webhooks/")

    def _payload(self, note: Notification) -> dict:
        sev = note.severity.value if hasattr(note.severity, "value") else str(note.severity)
        color = _SEVERITY_COLOR.get(sev, 0x95A5A6)
        description_parts = []
        if note.body:
            description_parts.append(note.body[:1900])   # Discord embed description cap is 4096
        fields = []
        fields.append({"name": "source", "value": f"`{note.source}`", "inline": True})
        fields.append({"name": "severity", "value": sev, "inline": True})
        fields.append({"name": "time (UTC)", "value": note.timestamp_utc, "inline": True})
        if note.context:
            ctx_text = "\n".join(f"**{k}**: `{v}`" for k, v in sorted(note.context.items()))
            fields.append({"name": "context", "value": ctx_text[:1000], "inline": False})
        embed = {
            "title": f"NexaQuant · {sev}",
            "description": (f"**{note.title}**\n\n" + "\n".join(description_parts))[:4000],
            "color": color,
            "fields": fields,
            "timestamp": note.timestamp_utc,
        }
        return {"embeds": [embed]}

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
            return 200 <= e.code < 300
        except Exception:
            return False


__all__ = ["DiscordChannel"]
