"""Notification abstraction.

A Notification is a structured message. A NotificationChannel is a delivery
mechanism (Telegram, File, later Email/Discord/Slack/Webhook). The manager
routes each Notification to every attached channel and reports per-channel
outcomes.

This layer knows NOTHING about pipeline stages; it just moves messages.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..events import Severity


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Notification:
    """A single message to be delivered."""
    timestamp_utc: str
    severity: Severity
    source: str          # e.g. "pipeline.stage.recommendation"
    title: str           # short one-liner
    body: str = ""       # longer body (optional)
    context: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "severity": self.severity.value if isinstance(self.severity, Severity)
                        else self.severity,
            "source": self.source,
            "title": self.title,
            "body": self.body,
            "context": self.context,
        }

    @classmethod
    def new(cls, severity: Severity, source: str, title: str,
            body: str = "", context: dict | None = None) -> "Notification":
        return cls(
            timestamp_utc=_iso_utc(),
            severity=severity,
            source=source,
            title=title,
            body=body,
            context=context or {},
        )


class NotificationChannel(ABC):
    """Abstract notification delivery mechanism."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used in logs and manager routing decisions."""

    @property
    def min_severity(self) -> Severity:
        """Minimum severity this channel accepts. Subclasses override."""
        return Severity.INFO

    def accepts(self, severity: Severity) -> bool:
        order = {Severity.INFO: 0, Severity.WARN: 1, Severity.CRITICAL: 2}
        return order.get(severity, 0) >= order.get(self.min_severity, 0)

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Deliver the notification. Return True on success, False on failure.
        Must NOT raise — swallow exceptions and log them; the manager needs
        every channel to be non-blocking for the ones after it."""
