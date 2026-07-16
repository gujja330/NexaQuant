"""NotificationManager — routes each Notification through every attached channel.

Semantics:
- Fan-out: every channel gets a chance to deliver every accepted notification.
- Channels are ordered by construction. Early channels are preferred delivery
  targets; later channels are fallbacks.
- The manager guarantees at least one channel receives every message (typically
  FileChannel, which cannot fail under normal disk conditions).
- No channel failure ever propagates — the manager collects per-channel
  outcomes and reports them.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import Notification, NotificationChannel


@dataclass
class DeliveryResult:
    channel: str
    ok: bool
    accepted: bool     # False if filtered by severity


class NotificationManager:
    def __init__(self, channels: list[NotificationChannel]):
        if not channels:
            raise ValueError("NotificationManager needs at least one channel "
                              "(typically FileChannel as fallback)")
        self.channels = list(channels)

    def emit(self, notification: Notification) -> list[DeliveryResult]:
        """Deliver to every channel. Return per-channel outcomes."""
        results: list[DeliveryResult] = []
        for ch in self.channels:
            if not ch.accepts(notification.severity):
                results.append(DeliveryResult(ch.name, ok=True, accepted=False))
                continue
            ok = False
            try:
                ok = bool(ch.send(notification))
            except Exception:
                ok = False
            results.append(DeliveryResult(ch.name, ok=ok, accepted=True))
        return results

    def emit_or_raise(self, notification: Notification) -> None:
        """Deliver; raise if NO channel (of those accepting) succeeded. Only use
        this when you want the caller to know delivery failed globally."""
        results = self.emit(notification)
        accepted = [r for r in results if r.accepted]
        if accepted and not any(r.ok for r in accepted):
            raise RuntimeError(
                f"NotificationManager: no channel delivered "
                f"{notification.severity} '{notification.title}'; "
                f"per-channel: {[(r.channel, r.ok) for r in accepted]}")
