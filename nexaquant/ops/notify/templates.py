"""OPS001-C · Notification templates.

Seven pre-built templates for the events NexaQuant emits routinely. Each
function returns a Notification with a consistent title / body / context
shape so downstream channels render uniformly.

Templates are PURE — they never touch the network or filesystem.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..events import Severity
from .base import Notification


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pipeline_success(*, pipeline: str, duration_s: float,
                      stages_ok: int, stages_total: int,
                      asof: str = "") -> Notification:
    return Notification.new(
        severity=Severity.INFO,
        source=f"pipeline.{pipeline}",
        title=f"Pipeline {pipeline} completed successfully",
        body=(f"All {stages_ok}/{stages_total} stages passed.\n"
              f"Duration: {duration_s:.1f}s\n"
              f"Latest asof: {asof or 'n/a'}"),
        context={"pipeline": pipeline, "duration_s": round(duration_s, 3),
                 "stages_ok": stages_ok, "stages_total": stages_total,
                 "asof": asof, "kind": "pipeline_success"},
    )


def pipeline_failure(*, pipeline: str, failed_stage: str, reason: str,
                      stages_ok: int, stages_total: int,
                      exit_code: int | None = None) -> Notification:
    return Notification.new(
        severity=Severity.ERROR,
        source=f"pipeline.{pipeline}.{failed_stage}",
        title=f"Pipeline {pipeline} FAILED at stage {failed_stage}",
        body=(f"Stage: {failed_stage}\n"
              f"Reason: {reason}\n"
              f"Progress: {stages_ok}/{stages_total} stages passed before failure\n"
              f"Exit code: {exit_code if exit_code is not None else 'n/a'}"),
        context={"pipeline": pipeline, "failed_stage": failed_stage,
                 "stages_ok": stages_ok, "stages_total": stages_total,
                 "exit_code": exit_code, "reason": reason[:512],
                 "kind": "pipeline_failure"},
    )


def mon001_halt(*, dimension: str, detail: str,
                 fingerprint_hash: str = "") -> Notification:
    return Notification.new(
        severity=Severity.CRITICAL,
        source=f"mon001.{dimension}",
        title=f"MON001 HALT — {dimension}",
        body=(f"Dimension: {dimension}\n"
              f"Detail: {detail}\n"
              f"Fingerprint: {fingerprint_hash[:16] + '...' if fingerprint_hash else 'n/a'}\n\n"
              f"Do NOT restart the daemon aggressively. See "
              f"docs/OPS001B_RECOVERY.md §5."),
        context={"dimension": dimension, "detail": detail[:512],
                 "fingerprint_hash": fingerprint_hash,
                 "kind": "mon001_halt"},
    )


def commissioning_failure(*, subsystem: str, reason: str,
                           report_ref: str = "") -> Notification:
    return Notification.new(
        severity=Severity.ERROR,
        source=f"commissioning.{subsystem}",
        title=f"OPS001.5 commissioning FAILED — {subsystem}",
        body=(f"Subsystem: {subsystem}\n"
              f"Reason: {reason}\n"
              f"See: {report_ref or 'docs/OPS001_5_COMMISSIONING_REPORT.md'}"),
        context={"subsystem": subsystem, "reason": reason[:512],
                 "report_ref": report_ref, "kind": "commissioning_failure"},
    )


def daemon_restart(*, reason: str, uptime_s: float,
                    ops_version: str = "") -> Notification:
    return Notification.new(
        severity=Severity.WARN,
        source="daemon",
        title="NexaQuant daemon restarted",
        body=(f"Reason: {reason}\n"
              f"Previous uptime: {uptime_s:.1f}s\n"
              f"OPS version: {ops_version or 'unknown'}"),
        context={"reason": reason[:512], "previous_uptime_s": round(uptime_s, 3),
                 "ops_version": ops_version, "kind": "daemon_restart"},
    )


def recovery_event(*, previous_phase: str, action: str, reason: str,
                    slot_name: str = "") -> Notification:
    return Notification.new(
        severity=Severity.WARN,
        source="daemon.recovery",
        title=f"Recovery decision: {action}",
        body=(f"Previous phase: {previous_phase}\n"
              f"Action: {action}\n"
              f"Reason: {reason}\n"
              f"Slot: {slot_name or 'n/a'}"),
        context={"previous_phase": previous_phase, "action": action,
                 "reason": reason[:512], "slot_name": slot_name,
                 "kind": "recovery_event"},
    )


def daily_summary(*, asof: str, pipelines_ok: int, pipelines_total: int,
                   mon001_state: str = "OK",
                   alerts_last_24h: int = 0) -> Notification:
    is_ok = pipelines_ok == pipelines_total and mon001_state == "OK" and alerts_last_24h == 0
    return Notification.new(
        severity=Severity.INFO if is_ok else Severity.WARN,
        source="daemon.summary.daily",
        title=f"Daily summary — {asof}",
        body=(f"asof: {asof}\n"
              f"Pipelines OK: {pipelines_ok}/{pipelines_total}\n"
              f"MON001 state: {mon001_state}\n"
              f"Alerts last 24h: {alerts_last_24h}"),
        context={"asof": asof, "pipelines_ok": pipelines_ok,
                 "pipelines_total": pipelines_total,
                 "mon001_state": mon001_state,
                 "alerts_last_24h": alerts_last_24h,
                 "kind": "daily_summary"},
    )


def weekly_summary(*, week_ending_asof: str,
                    trading_days: int,
                    pipelines_ok: int, pipelines_total: int,
                    mon001_halts: int = 0,
                    critical_alerts: int = 0) -> Notification:
    healthy = (pipelines_ok == pipelines_total and
                mon001_halts == 0 and critical_alerts == 0)
    return Notification.new(
        severity=Severity.INFO if healthy else Severity.WARN,
        source="daemon.summary.weekly",
        title=f"Weekly summary — week ending {week_ending_asof}",
        body=(f"Week ending: {week_ending_asof}\n"
              f"Trading days: {trading_days}\n"
              f"Pipeline success rate: {pipelines_ok}/{pipelines_total}\n"
              f"MON001 halts: {mon001_halts}\n"
              f"Critical alerts: {critical_alerts}"),
        context={"week_ending_asof": week_ending_asof,
                 "trading_days": trading_days,
                 "pipelines_ok": pipelines_ok,
                 "pipelines_total": pipelines_total,
                 "mon001_halts": mon001_halts,
                 "critical_alerts": critical_alerts,
                 "kind": "weekly_summary"},
    )


TEMPLATE_KINDS = (
    "pipeline_success", "pipeline_failure", "mon001_halt",
    "commissioning_failure", "daemon_restart", "recovery_event",
    "daily_summary", "weekly_summary",
)


__all__ = [
    "pipeline_success",
    "pipeline_failure",
    "mon001_halt",
    "commissioning_failure",
    "daemon_restart",
    "recovery_event",
    "daily_summary",
    "weekly_summary",
    "TEMPLATE_KINDS",
]
