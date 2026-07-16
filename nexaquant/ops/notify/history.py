"""OPS001-C · Notification history.

Reads the append-only JSONL that FileChannel writes, plus the retry-queue
delivered/DLQ ledgers, and produces:

- JSONL passthrough (already the on-disk format)
- CSV export (for spreadsheet tools)
- Markdown summary (for daily / weekly ops reports)

Read-only: never mutates the source files.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _parse_ts(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


@dataclass
class HistoryFilter:
    since_utc: datetime | None = None
    until_utc: datetime | None = None
    severity_in: tuple[str, ...] = ("INFO", "WARN", "ERROR", "CRITICAL")
    source_prefix: str = ""


def load_history(alerts_jsonl: Path,
                  flt: HistoryFilter | None = None) -> list[dict]:
    """Load alert rows from JSONL, applying an optional filter."""
    rows = _read_jsonl(alerts_jsonl)
    if flt is None:
        return rows
    out: list[dict] = []
    for r in rows:
        sev = str(r.get("severity", "")).upper()
        if sev not in flt.severity_in:
            continue
        if flt.source_prefix and not str(r.get("source", "")).startswith(flt.source_prefix):
            continue
        ts = _parse_ts(str(r.get("timestamp_utc", "")))
        if flt.since_utc and (ts is None or ts < flt.since_utc):
            continue
        if flt.until_utc and (ts is None or ts > flt.until_utc):
            continue
        out.append(r)
    return out


def to_csv(rows: list[dict]) -> str:
    """Convert alert rows to CSV. Uses a stable column set; extra keys are
    serialized into a `context` JSON column."""
    fixed = ("timestamp_utc", "severity", "source", "title", "body")
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(list(fixed) + ["context"])
    for r in rows:
        w.writerow([
            r.get("timestamp_utc", ""),
            r.get("severity", ""),
            r.get("source", ""),
            r.get("title", ""),
            (r.get("body", "") or "").replace("\n", " "),
            json.dumps(r.get("context", {}), ensure_ascii=False, default=str),
        ])
    return buf.getvalue()


def markdown_summary(rows: list[dict], *, title: str = "Notification history") -> str:
    """Produce a compact markdown report of alert counts by severity and top
    sources. Also lists the most recent 10 CRITICAL alerts."""
    lines = [f"# {title}", ""]
    if not rows:
        lines.append("_no alerts in range_")
        return "\n".join(lines) + "\n"

    lines.append(f"**Total events:** {len(rows)}")
    lines.append("")

    sev_counter = Counter(r.get("severity", "") for r in rows)
    src_counter = Counter(r.get("source", "").split(".")[0] for r in rows)

    lines.append("## By severity")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in ("INFO", "WARN", "ERROR", "CRITICAL"):
        lines.append(f"| {sev} | {sev_counter.get(sev, 0)} |")
    lines.append("")

    lines.append("## Top source prefixes")
    lines.append("")
    lines.append("| Source | Count |")
    lines.append("|---|---:|")
    for src, n in src_counter.most_common(10):
        lines.append(f"| `{src or '<unknown>'}` | {n} |")
    lines.append("")

    criticals = [r for r in rows if r.get("severity") == "CRITICAL"]
    criticals.sort(key=lambda r: r.get("timestamp_utc", ""), reverse=True)
    lines.append("## Recent CRITICAL events")
    lines.append("")
    if not criticals:
        lines.append("_none_")
    else:
        lines.append("| Time (UTC) | Source | Title |")
        lines.append("|---|---|---|")
        for r in criticals[:10]:
            lines.append(f"| {r.get('timestamp_utc', '')} | "
                          f"`{r.get('source', '')}` | {r.get('title', '')} |")
    lines.append("")

    return "\n".join(lines) + "\n"


__all__ = [
    "HistoryFilter",
    "load_history",
    "to_csv",
    "markdown_summary",
]
