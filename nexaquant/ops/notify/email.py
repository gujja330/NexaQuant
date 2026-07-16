"""OPS001-C · Email notification channel (SMTP, stdlib only).

Reads SMTP config from environment variables:
  NEXAQUANT_SMTP_HOST         — e.g. smtp.gmail.com
  NEXAQUANT_SMTP_PORT         — e.g. 587
  NEXAQUANT_SMTP_USER         — sender address
  NEXAQUANT_SMTP_PASSWORD     — app password / SMTP token
  NEXAQUANT_SMTP_FROM         — From: header (defaults to SMTP_USER)
  NEXAQUANT_SMTP_TO           — comma-separated recipient addresses
  NEXAQUANT_SMTP_USE_TLS      — "1"/"true" to enable STARTTLS (default: enabled)

When any required var is absent, `configured` is False and `send()` returns
False without contacting the network. FileChannel is the last-resort fallback.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from ..events import Severity
from .base import Notification, NotificationChannel


class EmailChannel(NotificationChannel):
    def __init__(self, min_severity: Severity = Severity.ERROR,
                  timeout_s: float = 20.0):
        self._min_severity = min_severity
        self.timeout_s = float(timeout_s)
        self.host = os.environ.get("NEXAQUANT_SMTP_HOST", "").strip()
        self.port = int(os.environ.get("NEXAQUANT_SMTP_PORT", "587") or 587)
        self.user = os.environ.get("NEXAQUANT_SMTP_USER", "").strip()
        self.password = os.environ.get("NEXAQUANT_SMTP_PASSWORD", "")
        self.sender = os.environ.get("NEXAQUANT_SMTP_FROM", "").strip() or self.user
        raw_to = os.environ.get("NEXAQUANT_SMTP_TO", "").strip()
        self.recipients = [x.strip() for x in raw_to.split(",") if x.strip()]
        self.use_tls = os.environ.get("NEXAQUANT_SMTP_USE_TLS", "1").lower() not in (
            "0", "false", "no", "")

    @property
    def name(self) -> str:
        return "email"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password
                    and self.sender and self.recipients)

    def _render(self, note: Notification) -> EmailMessage:
        msg = EmailMessage()
        sev = note.severity.value if hasattr(note.severity, "value") else str(note.severity)
        msg["Subject"] = f"[NexaQuant {sev}] {note.title}"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        # Plain-text body: title + severity + source + timestamp + body + context.
        lines = [
            f"Severity: {sev}",
            f"Source:   {note.source}",
            f"Time:     {note.timestamp_utc}",
            "",
            note.title,
            "",
        ]
        if note.body:
            lines.extend(note.body.splitlines())
            lines.append("")
        if note.context:
            lines.append("Context:")
            for k in sorted(note.context.keys()):
                lines.append(f"  {k}: {note.context[k]}")
        msg.set_content("\n".join(lines))
        return msg

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            return False
        try:
            msg = self._render(notification)
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_s) as s:
                if self.use_tls:
                    s.starttls(context=ctx)
                s.login(self.user, self.password)
                s.send_message(msg)
            return True
        except Exception:
            return False


__all__ = ["EmailChannel"]
