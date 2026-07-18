"""Institutional Memory · Immutable Daily Bundle archiver.

At the tail of each pipeline run, freeze the canonical decision surface
into `data/archive/YYYY/MM/DD/bundle/` and write a content-addressed
manifest. Never overwrites.

Every downstream research capability (Winner Genome, Alpha Signature,
Decision Attribution) reads its training corpus from this archive, NOT
from `reports/*.json` (which is a rolling frame).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_ROOT = _ROOT / "data" / "archive"
REPORTS_DIR  = _ROOT / "reports"

# Canonical files to freeze on every run.
# These together capture the complete decision surface at t=today.
CANONICAL_BUNDLE = [
    "recommendations.json",
    "investment_intelligence.json",
    "intelligence_summary.json",
    "intelligence_conflicts.json",
    "price_context.json",
    "risk_capital_v2_latest.json",
    "global_context.json",
    "champion_strategy.json",
    "confidence_calibration.json",
    "validation_v2_latest.json",
    "stock_validation.json",
    "knowledge_graph.json",
    "decision_center_today.json",
    "recommendation_dna_feedback.json",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 15), b""):
            h.update(chunk)
    return h.hexdigest()


def _code_sha() -> str:
    """Best-effort code fingerprint — falls back to '(dirty)' outside a git repo."""
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                             capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()[:12]
    except Exception:
        pass
    return "(unknown)"


def _target_dir_for(run_date: str | None = None) -> Path:
    """Resolve `data/archive/YYYY/MM/DD/bundle/` for a given ISO date (default: today)."""
    if run_date is None:
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    y, m, d = run_date.split("-")
    return ARCHIVE_ROOT / y / m / d / "bundle"


def archive_today(run_date: str | None = None, overwrite: bool = False) -> dict:
    """Freeze the canonical bundle for today (or `run_date`).

    Returns the manifest dict. Silent for missing optional files —
    just records them absent in the manifest.
    """
    if run_date is None:
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = _target_dir_for(run_date)
    if target.exists() and not overwrite:
        # Return the existing manifest — archive is immutable by design.
        m = target.parent / "manifest.json"
        if m.exists():
            return {"already_archived": True, **json.loads(m.read_text(encoding="utf-8"))}

    target.mkdir(parents=True, exist_ok=True)

    files_entry = []
    total_bytes = 0
    for name in CANONICAL_BUNDLE:
        src = REPORTS_DIR / name
        if not src.exists():
            files_entry.append({"name": name, "present": False, "sha256": None, "bytes": 0})
            continue
        dst = target / name
        shutil.copy2(src, dst)
        h = _sha256(dst)
        b = dst.stat().st_size
        total_bytes += b
        files_entry.append({"name": name, "present": True, "sha256": h, "bytes": b})

    manifest = {
        "run_date":    run_date,
        "run_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "code_sha":    _code_sha(),
        "engine":      "institutional_memory",
        "version":     "v1.0",
        "n_files":     sum(1 for f in files_entry if f["present"]),
        "total_bytes": total_bytes,
        "files":       files_entry,
        "immutable":   True,
    }
    m_path = target.parent / "manifest.json"
    m_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def list_archive_days(limit: int | None = None) -> list[str]:
    """Return sorted list of YYYY-MM-DD keys present in `data/archive/`."""
    days: list[str] = []
    if not ARCHIVE_ROOT.exists():
        return days
    for y in sorted(ARCHIVE_ROOT.iterdir()):
        if not y.is_dir(): continue
        for mo in sorted(y.iterdir()):
            if not mo.is_dir(): continue
            for d in sorted(mo.iterdir()):
                if not d.is_dir(): continue
                if (d / "manifest.json").exists() or (d / "bundle").exists():
                    days.append(f"{y.name}-{mo.name}-{d.name}")
    days.sort()
    return days[-limit:] if limit else days


def read_archive_bundle(run_date: str, filename: str) -> dict | None:
    """Read one file from an archived day's bundle. Returns None if not present."""
    y, m, d = run_date.split("-")
    p = ARCHIVE_ROOT / y / m / d / "bundle" / filename
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_archive_manifest(run_date: str) -> dict | None:
    y, m, d = run_date.split("-")
    p = ARCHIVE_ROOT / y / m / d / "manifest.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def build_monthly_digest(year: int, month: int) -> dict:
    """Aggregate all daily manifests in a given YYYY-MM into a single digest,
    intended to be committed to git as `reports/archive_digest_YYYY-MM.json`."""
    month_str = f"{month:02d}"
    year_str = str(year)
    month_dir = ARCHIVE_ROOT / year_str / month_str
    daily_manifests: list[dict] = []
    if month_dir.exists():
        for d in sorted(month_dir.iterdir()):
            m = d / "manifest.json"
            if m.exists():
                try:
                    daily_manifests.append(json.loads(m.read_text(encoding="utf-8")))
                except Exception:
                    pass
    return {
        "year":  year, "month": month,
        "n_days": len(daily_manifests),
        "run_dates": [m["run_date"] for m in daily_manifests],
        "manifests": daily_manifests,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
    }
