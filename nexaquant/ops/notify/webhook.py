"""OPS001-C · Generic HTTP webhook notification channel.

Reads config from environment:
  NEXAQUANT_WEBHOOK_URL           — target URL (POST). Required.
  NEXAQUANT_WEBHOOK_METHOD        — POST (default) / PUT
  NEXAQUANT_WEBHOOK_HEADERS       — JSON dict of extra headers (default: {})
  NEXAQUANT_WEBHOOK_AUTH_HEADER   — sensitive header line; kept separate for
                                    convenient bearer/api-key configuration
                                    (e.g. "Authorization: Bearer ...")

Payload is the Notification.as_dict() plus a "system": "nexaquant" marker.
Delivery is considered successful for any 2xx HTTP status.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..events import Severity
from .base import Notification, NotificationChannel


class WebhookChannel(NotificationChannel):
    def __init__(self, min_severity: Severity = Severity.CRITICAL,
                  timeout_s: float = 20.0):
        self._min_severity = min_severity
        self.timeout_s = float(timeout_s)
        self.url = os.environ.get("NEXAQUANT_WEBHOOK_URL", "").strip()
        self.method = (os.environ.get("NEXAQUANT_WEBHOOK_METHOD", "POST") or "POST").upper()
        raw_headers = os.environ.get("NEXAQUANT_WEBHOOK_HEADERS", "").strip()
        self.extra_headers: dict[str, str] = {}
        if raw_headers:
            try:
                parsed = json.loads(raw_headers)
                if isinstance(parsed, dict):
                    self.extra_headers = {str(k): str(v) for k, v in parsed.items()}
            except (ValueError, TypeError):
                pass
        # Convenience: single auth header string like "Authorization: Bearer ..."
        auth_line = os.environ.get("NEXAQUANT_WEBHOOK_AUTH_HEADER", "").strip()
        if auth_line and ":" in auth_line:
            k, _, v = auth_line.partition(":")
            self.extra_headers[k.strip()] = v.strip()

    @property
    def name(self) -> str:
        return "webhook"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    @property
    def configured(self) -> bool:
        return self.url.startswith("http://") or self.url.startswith("https://")

    def _payload(self, note: Notification) -> dict:
        data = note.as_dict()
        data["system"] = "nexaquant"
        return data

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            return False
        try:
            body = json.dumps(self._payload(notification)).encode("utf-8")
            headers = {"Content-Type": "application/json",
                       "User-Agent": "nexaquant-ops/0.1.0-ops001c"}
            headers.update(self.extra_headers)
            req = urllib.request.Request(self.url, data=body,
                                          headers=headers, method=self.method)
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            return 200 <= e.code < 300
        except Exception:
            return False


__all__ = ["WebhookChannel"]
