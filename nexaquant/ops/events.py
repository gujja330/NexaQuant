"""Stage lifecycle events.

Every pipeline stage broadcasts one of these events at each state transition.
Notification channels subscribe to the event stream via NotificationManager.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class StageEvent(str, Enum):
    """Stage lifecycle state. String-valued so events serialize cleanly to JSON."""
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    RETRY = "RETRY"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    COMPLETE = "COMPLETE"      # pipeline-level (all stages done)


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"          # OPS001-C: distinct from CRITICAL for finer escalation routing
    CRITICAL = "CRITICAL"


# Mapping of stage event to default severity. Consumers may override.
DEFAULT_SEVERITY: dict[StageEvent, Severity] = {
    StageEvent.STARTED: Severity.INFO,
    StageEvent.RUNNING: Severity.INFO,
    StageEvent.RETRY: Severity.WARN,
    StageEvent.FAILED: Severity.CRITICAL,
    StageEvent.SUCCESS: Severity.INFO,
    StageEvent.COMPLETE: Severity.INFO,
}


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Event:
    """A single lifecycle event emitted by the pipeline.

    Immutable-by-convention. Do not mutate after emission — the notification bus
    may read it asynchronously.
    """
    timestamp_utc: str
    kind: StageEvent
    severity: Severity
    stage: str            # stage name; empty string for pipeline-level events
    pipeline: str         # pipeline name
    attempt: int = 0
    max_attempts: int = 0
    duration_s: float | None = None
    exit_code: int | None = None
    reason: str = ""
    context: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "stage": self.stage,
            "pipeline": self.pipeline,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "duration_s": self.duration_s,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "context": self.context,
        }

    @classmethod
    def new(cls, kind: StageEvent, *, stage: str, pipeline: str,
            severity: Severity | None = None, **kwargs) -> "Event":
        return cls(
            timestamp_utc=_iso_utc(),
            kind=kind,
            severity=severity or DEFAULT_SEVERITY[kind],
            stage=stage,
            pipeline=pipeline,
            **kwargs,
        )
