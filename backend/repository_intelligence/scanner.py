"""Repository Intelligence Scanner · read-only forensic tool.

Emits a machine-readable report of dead code, orphan artifacts, and
staleness. Consumer decides what to delete.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_FINGERPRINT = "aegis.repository_intelligence.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.repository_intelligence.v1"

STALE_DAYS_DEFAULT = 30


@dataclass
class RepositoryFinding:
    category: str            # dead_module · orphan_report · stale_artifact · unused_config
    path: str
    reason: str
    severity: str            # LOW · MEDIUM · HIGH
    metadata: dict = field(default_factory=dict)


class RepositoryScanner:

    def __init__(self, repo_root: Path, stale_days: int = STALE_DAYS_DEFAULT):
        self.root = Path(repo_root).resolve()
        self.stale_days = stale_days

    def scan(self) -> dict:
        findings: list[RepositoryFinding] = []
        py_files = self._python_files()
        findings.extend(self._detect_orphan_reports())
        findings.extend(self._detect_stale_artifacts())
        findings.extend(self._detect_never_imported_modules(py_files))
        return {
            "engine": ENGINE_ID, "version": "1.0.0",
            "schema_version": SCHEMA_VERSION,
            "schema_fingerprint": SCHEMA_FINGERPRINT,
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "root": str(self.root),
            "n_findings": len(findings),
            "by_category": self._category_counts(findings),
            "findings": [asdict(f) for f in findings],
        }

    def _python_files(self) -> list[Path]:
        skip = ("__pycache__", ".git", "venv", "archive", "docs")
        out = []
        for p in self.root.rglob("*.py"):
            if any(s in p.parts for s in skip): continue
            out.append(p)
        return out

    def _detect_orphan_reports(self) -> list[RepositoryFinding]:
        """A .json in reports/ is orphan if no .py file in the tree mentions it."""
        out = []
        reports_dir = self.root / "reports"
        if not reports_dir.exists(): return out
        # Build a lightweight index of everything Python code mentions
        text_all = self._all_py_text()
        for jf in reports_dir.rglob("*.json"):
            if "history" in str(jf) or "archive" in str(jf): continue
            name = jf.name
            if name not in text_all:
                age_days = self._age_days(jf)
                out.append(RepositoryFinding(
                    category="orphan_report",
                    path=str(jf.relative_to(self.root)),
                    reason=f"no Python module references '{name}'",
                    severity="LOW",
                    metadata={"age_days": age_days},
                ))
        return out

    def _detect_stale_artifacts(self) -> list[RepositoryFinding]:
        out = []
        for f in (self.root / "reports").rglob("*") if (self.root/"reports").exists() else []:
            if not f.is_file(): continue
            if any(s in f.parts for s in ("history", "archive", "__pycache__")): continue
            age = self._age_days(f)
            if age > self.stale_days:
                out.append(RepositoryFinding(
                    category="stale_artifact",
                    path=str(f.relative_to(self.root)),
                    reason=f"age {age}d exceeds stale threshold {self.stale_days}d",
                    severity="MEDIUM" if age > 60 else "LOW",
                    metadata={"age_days": age},
                ))
        return out

    def _detect_never_imported_modules(self, py_files: list[Path]) -> list[RepositoryFinding]:
        """Any .py under backend/ that no other file imports · not counting
        entry-point runners named run.py or __main__."""
        out = []
        text_all = self._all_py_text()
        for p in py_files:
            if "backend" not in p.parts: continue
            if p.name in ("__init__.py", "run.py", "__main__.py"): continue
            # Convert to dotted module name
            rel = p.relative_to(self.root)
            mod_name = ".".join(rel.with_suffix("").parts)
            # Check both "from backend.x.y import" and "import backend.x.y"
            if mod_name not in text_all and rel.stem not in text_all:
                out.append(RepositoryFinding(
                    category="dead_module",
                    path=str(rel),
                    reason=f"no other Python file imports '{mod_name}'",
                    severity="LOW",   # LOW because may be test-only or planned
                    metadata={"module": mod_name},
                ))
        return out

    def _all_py_text(self) -> str:
        """Concatenate all Python source into a single string for grep-like checks."""
        chunks = []
        for p in self._python_files():
            try: chunks.append(p.read_text(encoding="utf-8", errors="replace"))
            except Exception: continue
        return "\n".join(chunks)

    def _age_days(self, f: Path) -> int:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            return (datetime.now(timezone.utc) - mtime).days
        except Exception: return 0

    def _category_counts(self, findings: list[RepositoryFinding]) -> dict[str, int]:
        c: dict[str, int] = {}
        for f in findings:
            c[f.category] = c.get(f.category, 0) + 1
        return c


def scan_repository(repo_root: Path | str, stale_days: int = STALE_DAYS_DEFAULT) -> dict:
    return RepositoryScanner(Path(repo_root), stale_days).scan()
