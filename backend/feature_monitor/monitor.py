"""Feature freshness + lineage + usage monitor."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.feature_monitor.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.feature_monitor.v1"

FRESHNESS_WARN_HOURS = 24
FRESHNESS_STALE_HOURS = 72


@dataclass
class FreshnessReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    n_raw: int = 0
    n_reports: int = 0
    fresh: int = 0
    warn: int = 0
    stale: int = 0
    unused: int = 0
    entries: list[dict] = field(default_factory=list)


class FeatureMonitor:

    def __init__(self, repo_root: Path):
        self.root = Path(repo_root).resolve()

    def scan(self) -> FreshnessReport:
        rep = FreshnessReport(run_utc=datetime.now(timezone.utc).isoformat())
        now = datetime.now(timezone.utc)
        # Raw data files
        for pattern in ("data/raw/india/*.parquet", "usa/data/raw/us/*.parquet"):
            for f in self.root.glob(pattern):
                age_h = (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).total_seconds() / 3600
                bucket = self._bucket(age_h)
                setattr(rep, bucket, getattr(rep, bucket) + 1)
                rep.n_raw += 1
                rep.entries.append({
                    "kind": "raw", "path": str(f.relative_to(self.root)),
                    "age_h": round(age_h, 2), "status": bucket,
                })
        # Reports
        for pattern in ("reports/*.json", "reports/*.parquet"):
            for f in self.root.glob(pattern):
                if "history" in f.parts: continue
                age_h = (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).total_seconds() / 3600
                bucket = self._bucket(age_h)
                setattr(rep, bucket, getattr(rep, bucket) + 1)
                rep.n_reports += 1
                rep.entries.append({
                    "kind": "report", "path": str(f.relative_to(self.root)),
                    "age_h": round(age_h, 2), "status": bucket,
                })
        return rep

    def _bucket(self, age_h: float) -> str:
        if age_h < FRESHNESS_WARN_HOURS: return "fresh"
        if age_h < FRESHNESS_STALE_HOURS: return "warn"
        return "stale"


def scan_freshness(repo_root: Path | str) -> dict:
    return asdict(FeatureMonitor(Path(repo_root)).scan())
