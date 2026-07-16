"""MetricsLedger — append-only operational telemetry.

Every stage completion appends one row. Never rewritten. Used later by the
OPS observability layer (OPS001-B/C) to compute trends, MTTR, availability.

Schema (per row, JSON):
- timestamp_utc: ISO string
- pipeline: name
- stage: name (empty for pipeline-level rows)
- kind: "stage" | "pipeline"
- success: bool
- attempts: int
- duration_s: float
- retry_count: int (attempts - 1)
- exit_code: int | None
- exception_type: str (empty if none)
- memory_kib: int | None (best-effort; None on platforms without resource)
- cpu_user_s: float | None (best-effort)
- context: dict (free-form)

Idempotent: repeated calls append rows; readers dedupe by (pipeline, stage, timestamp).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_rusage() -> tuple[int | None, float | None]:
    """Best-effort (memory_kib, cpu_user_s). None on Windows (no resource module)."""
    if sys.platform.startswith("win"):
        return None, None
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is KiB on Linux, bytes on macOS. Convert to KiB.
        mem = r.ru_maxrss
        if sys.platform == "darwin":
            mem = mem // 1024
        return int(mem), float(r.ru_utime)
    except Exception:
        return None, None


@dataclass
class MetricRow:
    timestamp_utc: str
    pipeline: str
    stage: str
    kind: str                       # "stage" | "pipeline"
    success: bool
    attempts: int
    duration_s: float
    retry_count: int
    exit_code: int | None = None
    exception_type: str = ""
    memory_kib: int | None = None
    cpu_user_s: float | None = None
    context: dict = field(default_factory=dict)


class MetricsLedger:
    """Append-only JSONL ledger. Path is a directory-relative file; parent is
    auto-created."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_stage(self, pipeline: str, stage: str, *,
                     success: bool, attempts: int, duration_s: float,
                     exit_code: int | None = None,
                     exception_type: str = "",
                     context: dict | None = None) -> MetricRow:
        mem, cpu = _read_rusage()
        row = MetricRow(
            timestamp_utc=_iso_utc(),
            pipeline=pipeline,
            stage=stage,
            kind="stage",
            success=bool(success),
            attempts=int(attempts),
            duration_s=float(duration_s),
            retry_count=max(0, int(attempts) - 1),
            exit_code=exit_code,
            exception_type=exception_type or "",
            memory_kib=mem,
            cpu_user_s=cpu,
            context=(context or {}),
        )
        self._append(row)
        return row

    def record_pipeline(self, pipeline: str, *, success: bool,
                        duration_s: float, stages_ok: int, stages_total: int,
                        context: dict | None = None) -> MetricRow:
        mem, cpu = _read_rusage()
        merged_ctx = dict(context or {})
        merged_ctx.setdefault("stages_ok", stages_ok)
        merged_ctx.setdefault("stages_total", stages_total)
        row = MetricRow(
            timestamp_utc=_iso_utc(),
            pipeline=pipeline,
            stage="",
            kind="pipeline",
            success=bool(success),
            attempts=1,
            duration_s=float(duration_s),
            retry_count=0,
            memory_kib=mem,
            cpu_user_s=cpu,
            context=merged_ctx,
        )
        self._append(row)
        return row

    def _append(self, row: MetricRow) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(row), ensure_ascii=False, default=str) + "\n")

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def recent(self, n: int = 100) -> list[dict]:
        return self.rows()[-n:]
