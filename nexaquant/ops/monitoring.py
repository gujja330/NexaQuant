"""OPS001-B runtime process monitoring.

Cross-platform. Prefers `psutil` when available (accurate CPU + memory + open
files), falls back to `resource` on POSIX and Windows Job APIs otherwise. If
neither is available, still reports uptime — never crashes.

All snapshots are safe to serialize into ops_status.json.metadata.
"""
from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore
    _HAS_PSUTIL = False


try:
    import resource  # type: ignore  # POSIX-only
    _HAS_RESOURCE = True
except ImportError:
    resource = None  # type: ignore
    _HAS_RESOURCE = False


@dataclass
class ProcessSnapshot:
    """A single-instant reading of the daemon process's health."""
    pid: int
    uptime_s: float
    memory_rss_mb: float
    memory_vms_mb: float
    cpu_percent: float
    num_threads: int
    open_files: int
    platform: str
    python: str
    source: str    # "psutil" / "resource" / "minimal"
    read_at_utc: str

    def as_dict(self) -> dict:
        return asdict(self)


class ProcessMonitor:
    """Sample the current process. Instantiate once; call snapshot() repeatedly."""

    def __init__(self) -> None:
        self._start_ts = time.time()
        self._proc = psutil.Process(os.getpid()) if _HAS_PSUTIL else None
        if self._proc is not None:
            # Prime cpu_percent — first call always returns 0.0
            try:
                self._proc.cpu_percent(interval=None)
            except Exception:
                pass

    @property
    def uptime_s(self) -> float:
        return max(0.0, time.time() - self._start_ts)

    def _psutil_snapshot(self) -> ProcessSnapshot:
        p = self._proc
        assert p is not None
        try:
            mem = p.memory_info()
            rss = mem.rss / (1024 * 1024)
            vms = mem.vms / (1024 * 1024)
        except Exception:
            rss = vms = 0.0
        try:
            cpu = float(p.cpu_percent(interval=None))
        except Exception:
            cpu = 0.0
        try:
            threads = int(p.num_threads())
        except Exception:
            threads = 0
        try:
            open_files = len(p.open_files())
        except Exception:
            open_files = 0
        return ProcessSnapshot(
            pid=os.getpid(),
            uptime_s=round(self.uptime_s, 3),
            memory_rss_mb=round(rss, 3),
            memory_vms_mb=round(vms, 3),
            cpu_percent=round(cpu, 2),
            num_threads=threads,
            open_files=open_files,
            platform=platform.platform(),
            python=sys.version.split()[0],
            source="psutil",
            read_at_utc=_iso_utc(),
        )

    def _resource_snapshot(self) -> ProcessSnapshot:
        rss_mb = 0.0
        cpu = 0.0
        try:
            ru = resource.getrusage(resource.RUSAGE_SELF)  # type: ignore[union-attr]
            # ru_maxrss is KB on Linux, bytes on macOS. Normalize by best guess.
            raw = float(ru.ru_maxrss)
            rss_mb = raw / (1024.0 if sys.platform == "linux" else 1024.0 * 1024.0)
            cpu = float(ru.ru_utime + ru.ru_stime)
        except Exception:
            pass
        return ProcessSnapshot(
            pid=os.getpid(),
            uptime_s=round(self.uptime_s, 3),
            memory_rss_mb=round(rss_mb, 3),
            memory_vms_mb=0.0,
            cpu_percent=round(cpu, 2),
            num_threads=0,
            open_files=0,
            platform=platform.platform(),
            python=sys.version.split()[0],
            source="resource",
            read_at_utc=_iso_utc(),
        )

    def _minimal_snapshot(self) -> ProcessSnapshot:
        return ProcessSnapshot(
            pid=os.getpid(),
            uptime_s=round(self.uptime_s, 3),
            memory_rss_mb=0.0,
            memory_vms_mb=0.0,
            cpu_percent=0.0,
            num_threads=0,
            open_files=0,
            platform=platform.platform(),
            python=sys.version.split()[0],
            source="minimal",
            read_at_utc=_iso_utc(),
        )

    def snapshot(self) -> ProcessSnapshot:
        if self._proc is not None:
            try:
                return self._psutil_snapshot()
            except Exception:
                pass
        if _HAS_RESOURCE:
            try:
                return self._resource_snapshot()
            except Exception:
                pass
        return self._minimal_snapshot()


@dataclass
class ExecutionTimings:
    """Rolling counters for stage latency and retry counts. Not thread-safe;
    the daemon is single-threaded by design."""
    total_runs: int = 0
    total_stage_runs: int = 0
    total_stage_retries: int = 0
    total_stage_failures: int = 0
    last_run_duration_s: float = 0.0
    last_stage_duration_s: dict = None  # type: ignore

    def __post_init__(self) -> None:
        if self.last_stage_duration_s is None:
            self.last_stage_duration_s = {}

    def record_run(self, duration_s: float, per_stage_seconds: dict[str, float],
                    retries: int, failures: int) -> None:
        self.total_runs += 1
        self.last_run_duration_s = float(duration_s)
        self.last_stage_duration_s = {k: float(v) for k, v in per_stage_seconds.items()}
        self.total_stage_runs += len(per_stage_seconds)
        self.total_stage_retries += int(retries)
        self.total_stage_failures += int(failures)

    def as_dict(self) -> dict:
        return asdict(self)


__all__ = [
    "ProcessSnapshot",
    "ProcessMonitor",
    "ExecutionTimings",
]
