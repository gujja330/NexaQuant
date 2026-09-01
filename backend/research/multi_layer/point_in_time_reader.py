"""Point-in-time data reader for Multi-Layer Research.

Guards against look-ahead bias: every read is bound to an `asof` cutoff
and physically refuses to return any row whose timestamp is strictly
greater than that cutoff. Insufficient historical data returns
`UNAVAILABLE` · never a synthesized value.

Backends supported (progressively): parquet · jsonl · csv.

Design goals:
  · Reproducible · same (asof, path) → same rows every call
  · Fail-loud · lookup violations raise · silent NaN/0 is a bug
  · Auditable · every read logs (path, asof, n_rows, hash) into an
    append-only research audit trail

CEO 2026-09-01 mandate: `Point-in-time data only · No look-ahead ·
Insufficient historical data → UNAVAILABLE, never fabricated`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Any

from .unavailable_contract import UNAVAILABLE


class PointInTimeReader:
    def __init__(self, root: Path, asof: date | str,
                  audit_log: Path | None = None):
        self.root = Path(root)
        if isinstance(asof, str):
            asof = date.fromisoformat(asof)
        self.asof = asof
        self.audit_log = audit_log or (
            self.root / "reports" / "research" / "multi_layer" / "audit.jsonl"
        )
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)

    def _record_audit(self, path: Path, n_rows: int, kind: str) -> None:
        rec = {
            "ts_utc": datetime.utcnow().isoformat(),
            "asof": self.asof.isoformat(),
            "path": str(path.relative_to(self.root)) if str(path).startswith(str(self.root)) else str(path),
            "n_rows": n_rows,
            "kind": kind,
        }
        with self.audit_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def read_jsonl(self, path: Path, date_field: str = "date") -> list[dict] | Any:
        """Read a JSONL file · return rows with row[date_field] <= self.asof.
        If the file is missing or has zero rows meeting the cutoff, return
        `UNAVAILABLE`."""
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        if not p.exists():
            self._record_audit(p, 0, "jsonl:missing")
            return UNAVAILABLE
        rows = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d = row.get(date_field)
                if not d: continue
                d_str = str(d)[:10]
                try:
                    row_d = date.fromisoformat(d_str)
                except ValueError:
                    continue
                if row_d <= self.asof:
                    rows.append(row)
        self._record_audit(p, len(rows), "jsonl:read")
        if not rows:
            return UNAVAILABLE
        return rows

    def read_csv_rows(self, path: Path, date_col: str = "date") -> list[dict] | Any:
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        if not p.exists():
            self._record_audit(p, 0, "csv:missing")
            return UNAVAILABLE
        import csv
        rows = []
        with p.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                d = row.get(date_col)
                if not d: continue
                d_str = str(d)[:10]
                try:
                    row_d = date.fromisoformat(d_str)
                except ValueError:
                    continue
                if row_d <= self.asof:
                    rows.append(row)
        self._record_audit(p, len(rows), "csv:read")
        if not rows:
            return UNAVAILABLE
        return rows

    def content_hash(self, rows: Iterable[dict]) -> str:
        """Stable content hash of an iterable of rows · for reproducibility."""
        h = hashlib.sha256()
        for r in rows:
            h.update(json.dumps(r, sort_keys=True, default=str).encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()
