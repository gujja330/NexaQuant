"""Pipeline orchestrator.

Executes stages in order (respecting depends_on when present), with per-stage
retries + backoff + timeout. Emits lifecycle events through the notification
bus. Writes per-stage metrics to the ledger.

Never raises. Always returns a PipelineResult. Callers inspect
`.success` to determine outcome.

Executes stages as subprocesses via `subprocess.run` with a bounded timeout.
This isolates each stage — a crashing stage does not kill the ops process.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import PipelineConfig, StageDefinition
from .events import Event, Severity, StageEvent
from .metrics import MetricsLedger
from .notify.base import Notification
from .notify.manager import NotificationManager
from .retry import RetryOutcome


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StageResult:
    stage: str
    success: bool
    attempts: int
    duration_s: float
    started_at_utc: str
    finished_at_utc: str
    exit_code: int | None = None
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)
    exception: str = ""
    skipped: bool = False
    skipped_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "stage": self.stage, "success": self.success, "attempts": self.attempts,
            "duration_s": self.duration_s, "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc, "exit_code": self.exit_code,
            "stdout_tail": self.stdout_tail, "stderr_tail": self.stderr_tail,
            "exception": self.exception, "skipped": self.skipped,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class PipelineResult:
    pipeline: str
    success: bool
    duration_s: float
    started_at_utc: str
    finished_at_utc: str
    stages: list[StageResult] = field(default_factory=list)

    @property
    def stages_ok(self) -> int:
        return sum(1 for s in self.stages if s.success and not s.skipped)

    @property
    def stages_total(self) -> int:
        return len(self.stages)

    def as_dict(self) -> dict:
        return {
            "pipeline": self.pipeline, "success": self.success,
            "duration_s": self.duration_s, "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "stages": [s.as_dict() for s in self.stages],
            "stages_ok": self.stages_ok, "stages_total": self.stages_total,
        }


# Callable used to execute a single stage attempt. Injectable so tests can
# replace the real subprocess with a fake.
StageRunner = Callable[[StageDefinition, float], tuple[int, str, str]]


def default_runner(stage: StageDefinition, timeout_s: float,
                   repo_root: Path | None = None) -> tuple[int, str, str]:
    """Real subprocess runner. Returns (exit_code, stdout, stderr).

    Timeout enforced by subprocess.run's timeout kwarg. On timeout, raises
    subprocess.TimeoutExpired which the pipeline treats as an attempt failure.
    """
    env = dict(os.environ)
    env.update(stage.env or {})
    cwd = stage.cwd or (str(repo_root) if repo_root is not None else None)
    r = subprocess.run(
        stage.command, env=env, cwd=cwd,
        capture_output=True, text=True, timeout=timeout_s,
    )
    return r.returncode, r.stdout or "", r.stderr or ""


class Pipeline:
    """Runs a PipelineConfig once. Never raises."""

    def __init__(self, config: PipelineConfig,
                 notifier: NotificationManager,
                 metrics: MetricsLedger,
                 runner: StageRunner | None = None,
                 repo_root: Path | None = None,
                 sleeper: Callable[[float], None] | None = None):
        self.config = config
        self.notifier = notifier
        self.metrics = metrics
        self.runner = runner or (lambda s, t: default_runner(s, t, repo_root))
        self.repo_root = repo_root
        self._sleep = sleeper or time.sleep

    def run(self) -> PipelineResult:
        t_pipeline_start = time.perf_counter()
        started = _iso_utc()
        results: list[StageResult] = []
        upstream_ok: dict[str, bool] = {}

        self._emit_event(Event.new(StageEvent.STARTED, stage="", pipeline=self.config.name))

        for stage in self.config.stages:
            # Dependency check
            unmet = [d for d in stage.depends_on if not upstream_ok.get(d, False)]
            if unmet:
                sr = StageResult(
                    stage=stage.name, success=False, attempts=0,
                    duration_s=0.0, started_at_utc=_iso_utc(),
                    finished_at_utc=_iso_utc(), skipped=True,
                    skipped_reason=f"depends_on unmet: {unmet}",
                )
                results.append(sr)
                self.metrics.record_stage(
                    self.config.name, stage.name,
                    success=False, attempts=0, duration_s=0.0,
                    exception_type="dependency_unmet",
                    context={"unmet": unmet})
                self._emit_event(Event.new(
                    StageEvent.FAILED, stage=stage.name, pipeline=self.config.name,
                    reason=f"skipped: depends_on unmet: {unmet}"))
                upstream_ok[stage.name] = False
                continue

            sr = self._run_stage(stage)
            results.append(sr)
            upstream_ok[stage.name] = sr.success

            # Short-circuit on failure unless continue_on_failure is set
            if not sr.success and not stage.continue_on_failure:
                # Mark remaining stages as skipped in the result set — but still
                # record them so metrics + status reflect reality.
                remaining_names = {s.name for s in self.config.stages}
                completed = {r.stage for r in results}
                for future_stage in self.config.stages:
                    if future_stage.name in completed:
                        continue
                    skipped = StageResult(
                        stage=future_stage.name, success=False, attempts=0,
                        duration_s=0.0, started_at_utc=_iso_utc(),
                        finished_at_utc=_iso_utc(), skipped=True,
                        skipped_reason=f"upstream stage '{stage.name}' failed",
                    )
                    results.append(skipped)
                    self.metrics.record_stage(
                        self.config.name, future_stage.name,
                        success=False, attempts=0, duration_s=0.0,
                        exception_type="upstream_failure",
                        context={"failed_upstream": stage.name})
                break

        finished = _iso_utc()
        duration = time.perf_counter() - t_pipeline_start
        pipeline_success = all(r.success for r in results if not r.skipped) \
                            and any(r.success for r in results)

        self.metrics.record_pipeline(
            self.config.name,
            success=pipeline_success,
            duration_s=duration,
            stages_ok=sum(1 for r in results if r.success and not r.skipped),
            stages_total=len(results),
        )
        self._emit_event(Event.new(
            StageEvent.COMPLETE, stage="", pipeline=self.config.name,
            duration_s=duration,
            reason=("all stages passed" if pipeline_success else "one or more stages failed"),
        ))
        # Terminal notification
        severity = Severity.INFO if pipeline_success else Severity.CRITICAL
        title = (f"Pipeline '{self.config.name}' PASSED" if pipeline_success
                 else f"Pipeline '{self.config.name}' FAILED")
        body_lines = [f"duration: {duration:.2f}s"]
        for r in results:
            marker = "OK" if r.success else ("SKIP" if r.skipped else "FAIL")
            body_lines.append(f"  [{marker}] {r.stage} ({r.attempts} attempt(s), "
                              f"{r.duration_s:.2f}s)")
        self.notifier.emit(Notification.new(
            severity=severity, source=f"pipeline.{self.config.name}",
            title=title, body="\n".join(body_lines),
            context={"stages_ok": sum(1 for r in results if r.success and not r.skipped),
                     "stages_total": len(results)},
        ))

        return PipelineResult(
            pipeline=self.config.name, success=pipeline_success,
            duration_s=duration, started_at_utc=started, finished_at_utc=finished,
            stages=results,
        )

    def _run_stage(self, stage: StageDefinition) -> StageResult:
        started = _iso_utc()
        t_stage_start = time.perf_counter()
        self._emit_event(Event.new(StageEvent.STARTED, stage=stage.name,
                                     pipeline=self.config.name,
                                     max_attempts=stage.retry.max_attempts))
        last_exit_code: int | None = None
        last_exception: str = ""
        last_stdout_tail: list[str] = []
        last_stderr_tail: list[str] = []
        attempt = 0
        while attempt < stage.retry.max_attempts:
            attempt += 1
            # Sleep BEFORE all attempts after the first
            if attempt > 1:
                wait = stage.retry.sleep_before_attempt(attempt)
                if wait > 0:
                    self._emit_event(Event.new(
                        StageEvent.RETRY, stage=stage.name,
                        pipeline=self.config.name, attempt=attempt,
                        max_attempts=stage.retry.max_attempts,
                        reason=f"sleeping {wait:.1f}s before attempt {attempt}"))
                    self._sleep(wait)

            self._emit_event(Event.new(
                StageEvent.RUNNING, stage=stage.name, pipeline=self.config.name,
                attempt=attempt, max_attempts=stage.retry.max_attempts))
            try:
                exit_code, stdout, stderr = self.runner(
                    stage, stage.retry.timeout_per_attempt_s)
                last_exit_code = exit_code
                last_stdout_tail = stdout.splitlines()[-10:] if stdout else []
                last_stderr_tail = stderr.splitlines()[-10:] if stderr else []
                if exit_code == 0:
                    duration = time.perf_counter() - t_stage_start
                    self.metrics.record_stage(
                        self.config.name, stage.name,
                        success=True, attempts=attempt,
                        duration_s=duration, exit_code=exit_code,
                        context={"stdout_tail": last_stdout_tail[-3:]})
                    self._emit_event(Event.new(
                        StageEvent.SUCCESS, stage=stage.name,
                        pipeline=self.config.name, attempt=attempt,
                        max_attempts=stage.retry.max_attempts,
                        duration_s=duration, exit_code=exit_code))
                    return StageResult(
                        stage=stage.name, success=True, attempts=attempt,
                        duration_s=duration, started_at_utc=started,
                        finished_at_utc=_iso_utc(), exit_code=exit_code,
                        stdout_tail=last_stdout_tail, stderr_tail=last_stderr_tail,
                    )
                # Non-zero exit code: retryable
                last_exception = f"non-zero exit code {exit_code}"
            except subprocess.TimeoutExpired as e:
                last_exit_code = None
                last_exception = f"TimeoutExpired after {e.timeout}s"
                last_stderr_tail = [f"[timeout] stage exceeded {e.timeout}s"]
            except Exception as e:
                last_exit_code = None
                last_exception = f"{type(e).__name__}: {e}"
                last_stderr_tail = [last_exception]

        duration = time.perf_counter() - t_stage_start
        self.metrics.record_stage(
            self.config.name, stage.name, success=False, attempts=attempt,
            duration_s=duration, exit_code=last_exit_code,
            exception_type=last_exception,
            context={"stderr_tail": last_stderr_tail[-3:]})
        self._emit_event(Event.new(
            StageEvent.FAILED, stage=stage.name, pipeline=self.config.name,
            attempt=attempt, max_attempts=stage.retry.max_attempts,
            duration_s=duration, exit_code=last_exit_code,
            reason=last_exception))
        return StageResult(
            stage=stage.name, success=False, attempts=attempt,
            duration_s=duration, started_at_utc=started,
            finished_at_utc=_iso_utc(), exit_code=last_exit_code,
            stdout_tail=last_stdout_tail, stderr_tail=last_stderr_tail,
            exception=last_exception,
        )

    def _emit_event(self, event: Event) -> None:
        """Broadcast lifecycle event as a notification. Never propagates errors."""
        try:
            severity = event.severity
            title = f"{event.pipeline}:{event.stage or '<pipeline>'} {event.kind.value}"
            body = event.reason
            self.notifier.emit(Notification.new(
                severity=severity, source=f"pipeline.{event.pipeline}.{event.stage or 'pipeline'}",
                title=title, body=body, context=event.as_dict(),
            ))
        except Exception:
            # Notification bus must never take down the pipeline.
            pass
