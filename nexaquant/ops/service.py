"""NexaQuantService — service wrapper around Pipeline + StatusWriter + Notifier.

Runs one pipeline pass. Writes status. Emits notifications. Never crashes.
Not a daemon — that's OPS001-B. This is the reusable framework a daemon (or
cron entrypoint, or Task Scheduler entry) will invoke.

Contract:
- `run_once()` returns 0 on pipeline success, non-zero on pipeline failure.
- Any internal error is caught, alerted, and returns 2 (framework error).
- Always writes ops_status.json before returning.
- Always releases lock if held.
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__ as _ops_pkg_version
from .config import load_pipeline
from .events import Severity


def _ops_version() -> str:
    return _ops_pkg_version
from .metrics import MetricsLedger
from .notify.base import Notification
from .notify.file import FileChannel
from .notify.manager import NotificationManager
from .notify.telegram import TelegramChannel
from .pipeline import Pipeline
from .status import StatusSnapshot, StatusWriter


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ServiceConfig:
    """Where to find the pipeline YAML + where to write outputs.

    All paths default to the repo layout established by earlier ENG/MON phases.
    """
    repo_root: Path
    pipeline_config: Path
    status_path: Path
    metrics_path: Path
    alerts_path: Path
    include_telegram: bool = True     # OPS001-A: Telegram + File. OPS001-C adds more.


def default_config(repo_root: Path, pipeline_config: Path | None = None) -> ServiceConfig:
    repo_root = Path(repo_root).resolve()
    reports = repo_root / "reports"
    return ServiceConfig(
        repo_root=repo_root,
        pipeline_config=Path(pipeline_config) if pipeline_config
                        else repo_root / "nexaquant" / "ops" / "pipelines" / "aegis_daily.yaml",
        status_path=reports / "ops_status.json",
        metrics_path=reports / "ops_metrics.jsonl",
        alerts_path=reports / "ops_alerts.jsonl",
    )


class NexaQuantService:
    """Load config, run pipeline once, write status. Never raises."""

    def __init__(self, config: ServiceConfig):
        self.config = config
        self._start_utc = datetime.now(timezone.utc)

    def _build_notifier(self) -> NotificationManager:
        channels = [FileChannel(self.config.alerts_path, min_severity=Severity.INFO)]
        if self.config.include_telegram:
            tg = TelegramChannel(min_severity=Severity.WARN)
            # Only include Telegram if configured. Unconfigured Telegram would
            # return False on every send — noise. FileChannel is always the
            # reliable fallback.
            if tg.configured:
                channels.append(tg)
        return NotificationManager(channels=channels)

    def _mon001_snapshot(self) -> dict:
        """Best-effort read of MON001 sealed fingerprint + latest diagnostics.
        Never raises. Returns {} on any failure."""
        try:
            sealed = json.loads(
                (self.config.repo_root
                 / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json"
                 ).read_text(encoding="utf-8"))
            fp_hash = sealed.get("hash", "")
            algo = int(sealed.get("algorithm_version", 0))
        except Exception:
            fp_hash, algo = "", 0

        state, halt, broker, last_asof = "UNKNOWN", False, "PAPER_ONLY", ""
        try:
            reports_dir = (self.config.repo_root
                           / "india/monitoring/MON001_Forward_Validation/reports")
            diagnostics = sorted(reports_dir.glob("mon001_diagnostics_*.json"))
            if diagnostics:
                d = json.loads(diagnostics[-1].read_text(encoding="utf-8"))
                state = d.get("global_state", state)
                halt = bool(d.get("halt_review_required", halt))
                bs = d.get("broker_status", {})
                broker = "PAPER_ONLY" if not bs.get("available", False) else "BROKER_ACTIVE"
        except Exception:
            pass

        try:
            reg_path = self.config.repo_root / "data" / "aegis_registry.csv"
            if reg_path.exists():
                # Last line's asof column (index 2 in CSV)
                with reg_path.open("r", encoding="utf-8") as f:
                    tail = f.readlines()[-1].strip().split(",")
                    if len(tail) > 2:
                        last_asof = tail[2]
        except Exception:
            pass

        return {"fingerprint_hash": fp_hash, "algorithm_version": algo,
                "state": state, "halt": halt, "broker": broker,
                "last_asof": last_asof}

    def run_once(self) -> int:
        """Execute the pipeline once. Return 0 on success, 1 on pipeline failure,
        2 on framework failure. Always writes ops_status.json."""
        notifier: NotificationManager | None = None
        status_writer: StatusWriter | None = None
        pipeline_result_dict: dict | None = None
        pipeline_success = False
        pipeline_name = "<unknown>"

        try:
            notifier = self._build_notifier()
            metrics = MetricsLedger(self.config.metrics_path)
            status_writer = StatusWriter(self.config.status_path, self.config.repo_root)

            pipeline_config = load_pipeline(self.config.pipeline_config)
            pipeline_name = pipeline_config.name

            pipeline = Pipeline(
                config=pipeline_config,
                notifier=notifier,
                metrics=metrics,
                repo_root=self.config.repo_root,
            )
            result = pipeline.run()
            pipeline_result_dict = result.as_dict()
            pipeline_success = result.success

            self._write_status(status_writer, pipeline_name, result)
            return 0 if pipeline_success else 1

        except Exception:
            tb = traceback.format_exc()
            if notifier is not None:
                try:
                    notifier.emit(Notification.new(
                        severity=Severity.CRITICAL,
                        source="ops.service",
                        title=f"NexaQuantService framework error ({pipeline_name})",
                        body=tb,
                    ))
                except Exception:
                    pass
            if status_writer is not None:
                try:
                    snap = StatusSnapshot(
                        pipeline_name=pipeline_name,
                        last_pipeline_success=False,
                        last_pipeline_run_utc=_iso_utc(),
                        stages_ok=0, stages_total=0,
                        ops_version=_ops_version(),
                        active_alerts=[{"source": "ops.service",
                                         "severity": "CRITICAL",
                                         "reason": tb.splitlines()[-1] if tb else ""}],
                        **self._mon001_snapshot_kwargs(),
                    )
                    status_writer.write(snap)
                except Exception:
                    pass
            return 2

    def _write_status(self, writer: StatusWriter,
                       pipeline_name: str, result) -> None:
        mon = self._mon001_snapshot()
        active_alerts: list[dict] = []
        for s in result.stages:
            if not s.success and not s.skipped:
                active_alerts.append({
                    "source": f"pipeline.{pipeline_name}.{s.stage}",
                    "severity": "CRITICAL",
                    "reason": s.exception or f"exit code {s.exit_code}",
                })
        snap = StatusSnapshot(
            pipeline_name=pipeline_name,
            last_pipeline_success=result.success,
            last_pipeline_run_utc=result.finished_at_utc,
            last_pipeline_duration_s=result.duration_s,
            stages_ok=result.stages_ok,
            stages_total=result.stages_total,
            ops_version=_ops_version(),
            active_alerts=active_alerts,
            mon001_state=mon["state"],
            mon001_halt=mon["halt"],
            mon001_fingerprint_hash=mon["fingerprint_hash"],
            mon001_algorithm_version=mon["algorithm_version"],
            broker_status=mon["broker"],
            recommendation_last_asof=mon["last_asof"],
        )
        writer.write(snap)

    def _mon001_snapshot_kwargs(self) -> dict:
        mon = self._mon001_snapshot()
        return {
            "mon001_state": mon["state"],
            "mon001_halt": mon["halt"],
            "mon001_fingerprint_hash": mon["fingerprint_hash"],
            "mon001_algorithm_version": mon["algorithm_version"],
            "broker_status": mon["broker"],
            "recommendation_last_asof": mon["last_asof"],
        }
