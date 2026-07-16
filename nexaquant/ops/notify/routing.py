"""OPS001-C · Routing + escalation policy.

Rules-based routing: given a Notification's severity, decide which channels
(by name) should attempt delivery. The policy is a plain dict, easy to
override from YAML, and does NOT need to know about the specific channel
implementations — it just returns names.

The default policy mirrors the spec:
  WARN     -> telegram, file
  ERROR    -> telegram, email, file
  CRITICAL -> telegram, email, slack, discord, webhook, file
  INFO     -> file           (recorded only; not paged)
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Iterable

from ..events import Severity


DEFAULT_POLICY: dict[str, list[str]] = {
    "INFO":     ["file"],
    "WARN":     ["telegram", "file"],
    "ERROR":    ["telegram", "email", "file"],
    "CRITICAL": ["telegram", "email", "slack", "discord", "webhook", "file"],
}


@dataclass
class RoutingPolicy:
    """Severity -> list of channel names to attempt.

    `include_file_fallback` guarantees the FileChannel is always in the list
    even if a caller-provided policy omits it — FileChannel is the durable
    audit trail and must never be skipped.
    """
    per_severity: dict[str, list[str]] = field(default_factory=dict)
    include_file_fallback: bool = True

    @classmethod
    def default(cls) -> "RoutingPolicy":
        return cls(per_severity=copy.deepcopy(DEFAULT_POLICY))

    @classmethod
    def from_dict(cls, spec: dict) -> "RoutingPolicy":
        """Parse a dict of the form {"CRITICAL": ["telegram", "email"], ...}.
        Missing severities inherit from DEFAULT_POLICY. Unknown severities
        are ignored (do not raise)."""
        merged = copy.deepcopy(DEFAULT_POLICY)
        for k, v in (spec or {}).items():
            key = str(k).upper()
            if key in DEFAULT_POLICY and isinstance(v, list):
                merged[key] = [str(x).strip() for x in v if str(x).strip()]
        return cls(per_severity=merged)

    def channels_for(self, severity: Severity | str) -> list[str]:
        sev = severity.value if isinstance(severity, Severity) else str(severity).upper()
        out = list(self.per_severity.get(sev, []))
        if self.include_file_fallback and "file" not in out:
            out.append("file")
        # Dedup while preserving order.
        seen = set()
        result = []
        for name in out:
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result


@dataclass
class EscalationPolicy:
    """Escalation is expressed as an ORDERED list of channel names per
    severity, with the semantic that the delivery attempt walks this list
    in order and STOPS after the first success (unless `require_all=True`).

    The default is `require_all=True` — every listed channel must attempt
    delivery (fan-out semantics). This matches the spec: CRITICAL fans out
    to every channel.
    """
    per_severity: dict[str, list[str]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_POLICY))
    require_all: bool = True

    def channels_for(self, severity: Severity | str) -> list[str]:
        sev = severity.value if isinstance(severity, Severity) else str(severity).upper()
        return list(self.per_severity.get(sev, ["file"]))


def resolve_channels(policy: RoutingPolicy, available: Iterable[str],
                      severity: Severity | str) -> list[str]:
    """Given a policy, the set of channels the operator has actually wired up,
    and a severity, return the ORDERED list of channel names to route to.

    Preserves the policy's channel order. Silently drops channels that aren't
    in `available` — but if the policy names a channel that is not wired,
    that's still logged upstream so the operator sees the config gap."""
    available_set = set(available)
    channels = policy.channels_for(severity)
    return [c for c in channels if c in available_set]


__all__ = [
    "DEFAULT_POLICY",
    "RoutingPolicy",
    "EscalationPolicy",
    "resolve_channels",
]
