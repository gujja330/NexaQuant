"""OPS status endpoint — writes reports/ops_status.json.

A single JSON file summarizing the operational state. Read-only from the
consumer's perspective; the ops service atomically rewrites it after every
pipeline pass.

Schema is stable; new fields are added over time but existing ones are never
renamed or repurposed. Dashboards / observability tools depend on the shape.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_sha(repo_root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "unknown"


@dataclass
class StatusSnapshot:
    """Single serializable status object."""
    schema_version: int = 1
    written_at_utc: str = ""
    ops_version: str = ""
    git_sha: str = ""
    pipeline_name: str = ""
    last_pipeline_success: bool = False
    last_pipeline_run_utc: str = ""
    last_pipeline_duration_s: float = 0.0
    stages_ok: int = 0
    stages_total: int = 0
    next_run_scheduled_utc: str = ""
    active_alerts: list[dict] = field(default_factory=list)
    mon001_state: str = "UNKNOWN"
    mon001_halt: bool = False
    mon001_fingerprint_hash: str = ""
    mon001_algorithm_version: int = 0
    broker_status: str = "PAPER_ONLY"
    recommendation_last_asof: str = ""
    ops_uptime_s: float = 0.0
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = path.parent
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=tmp_dir,
                                       delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str, sort_keys=True)
        tmp_path = Path(f.name)
    os.replace(tmp_path, path)


class StatusWriter:
    """Owns the ops_status.json file. Reads existing state on start (so
    ops_uptime_s survives across runs) and writes atomically on update."""

    def __init__(self, path: Path | str, repo_root: Path):
        self.path = Path(path)
        self.repo_root = Path(repo_root)
        self._process_start_utc = datetime.now(timezone.utc)

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def write(self, snapshot: StatusSnapshot) -> Path:
        snapshot.written_at_utc = _iso_utc()
        snapshot.git_sha = _git_sha(self.repo_root)
        snapshot.ops_uptime_s = round(
            (datetime.now(timezone.utc) - self._process_start_utc).total_seconds(), 3)
        _atomic_write_json(self.path, snapshot.as_dict())
        return self.path
