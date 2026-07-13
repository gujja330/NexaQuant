"""
MON001 reporting layer — machine-readable diagnostics JSON + human-readable Markdown.

Deterministic writer. Never mutates existing reports; each run produces a new dated file.
Also maintains an append-only alerts JSONL for downstream integration.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from .monitor import MonitorReport


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_diagnostics_json(report: MonitorReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.as_dict(), sort_keys=True, ensure_ascii=False, indent=2,
                    default=str),
        encoding="utf-8")


def append_alert(alert_dict: dict, alerts_path: Path) -> None:
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    alert_dict = dict(alert_dict)
    alert_dict["appended_at_utc"] = _iso_utc()
    with alerts_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(alert_dict, sort_keys=True, ensure_ascii=False,
                            default=str) + "\n")


def render_markdown(report: MonitorReport) -> str:
    lines = [
        f"# MON001 · Forward Paper-Trading + Monitoring — {report.run_date_utc[:10]}",
        "",
        f"_Generated {report.run_date_utc}_",
        "",
        f"- **Global state:** `{report.global_state}`",
        f"- **HALT_REVIEW_REQUIRED:** `{report.halt_review_required}`",
        f"- **Forward boundary:** `{report.forward_boundary_asof}`",
        f"- **Forward days accumulated:** {report.forward_days_accumulated}",
        f"- **Forward recommendations ingested:** {report.forward_recs_ingested}",
        f"- **Completed cycles:** {report.completed_cycles}",
        f"- **Fingerprint status:** `{report.fingerprint_status}`",
        f"- **Fingerprint (sealed):** `{report.fingerprint_hash_sealed}`",
        f"- **Fingerprint (current):** `{report.fingerprint_hash_current}`",
        f"- **Baseline envelope hash:** `{report.baseline_envelope_hash}`",
        f"- **Broker status:** `{report.broker_status.get('available')}` — {report.broker_status.get('reason')}",
        "",
        "## Reason",
        "",
        report.reason,
        "",
        "## Ledger integrity",
        "",
        f"- ok: `{report.ledger_integrity.get('ok')}`",
        f"- rows_checked: `{report.ledger_integrity.get('rows_checked')}`",
        f"- reason: `{report.ledger_integrity.get('reason')}`",
        "",
        "## Metric evidence",
        "",
        "| Metric | Forward | Envelope [min, median, max] | Sample | Min req | Status | Reason |",
        "|---|---:|---|---:|---:|:-:|---|",
    ]
    for e in report.metric_evidence:
        env_str = (
            f"[{_fmt(e.envelope_min)}, {_fmt(e.envelope_median)}, {_fmt(e.envelope_max)}]"
            if e.envelope_median is not None else "—"
        )
        lines.append(
            f"| {e.metric} | {_fmt(e.forward_value)} | {env_str} | "
            f"{e.sample_size} | {e.minimum_required} | `{e.status}` | {e.reason} |")

    lines.append("")
    lines.append("## Drift alerts")
    lines.append("")
    if not report.drift_alerts:
        lines.append("_No active drift alerts._")
    else:
        lines.append("| Dimension | Level | Consecutive reports | First seen | Reason |")
        lines.append("|---|:-:|:-:|:-:|---|")
        for a in report.drift_alerts:
            lines.append(
                f"| {a.dimension} | `{a.level}` | {a.consecutive_reports} | "
                f"{a.first_seen or '—'} | {a.reason} |")

    lines.append("")
    lines.append("## Governance")
    lines.append("")
    lines.append("- MON001 does NOT modify production configuration.")
    lines.append("- MON001 does NOT increment `cumulative_strategy_search`.")
    lines.append("- HALT_REVIEW_REQUIRED is an operator-review signal, NOT an automatic action.")
    lines.append("")
    return "\n".join(lines)


def _fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            return "—"
        return f"{x:.4f}"
    return str(x)


def write_markdown(report: MonitorReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
