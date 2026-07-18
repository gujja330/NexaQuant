"""
MON001 operator dashboard — deterministic markdown summary.

Reads the latest diagnostics JSON + alerts JSONL + ledger and emits one dashboard file
per invocation. Never modifies any monitored file. Never places orders.

Run:
    python -m india.monitoring.MON001_Forward_Validation.ops.dashboard
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from india.monitoring.MON001_Forward_Validation.forward_ledger import ForwardLedger
from india.monitoring.MON001_Forward_Validation.ops.alerts import AlertBus


HERE = Path(__file__).resolve().parent.parent


def _fmt(x, kind="num"):
    if x is None:
        return "—"
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            return "—"
        if kind == "pct":
            return f"{x*100:+.2f}%"
        return f"{x:.4f}"
    return str(x)


def _remaining_days(current: int, target: int) -> int:
    return max(0, target - current)


def _load_latest_diagnostics(reports_dir: Path) -> dict | None:
    files = sorted(reports_dir.glob("mon001_diagnostics_*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def build_dashboard() -> str:
    with (HERE / "mon001.yaml").open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    reports_dir = ROOT / cfg["reporting"]["output_dir"]
    latest = _load_latest_diagnostics(reports_dir)
    ledger = ForwardLedger(
        ROOT / cfg["forward_ledger"]["path"],
        ROOT / cfg["forward_ledger"]["corrections_path"],
        cfg["forward_boundary_asof"])
    ledger_rows = ledger.rows()
    integrity = ledger.verify_chain()
    alerts_path = ROOT / cfg["reporting"]["alerts_path"]
    bus = AlertBus(alerts_path)
    active_alerts = bus.active("WARN")

    latest_asof = max((r["asof"] for r in ledger_rows), default="—")
    # Every field below uses .get() with a default so partial payloads
    # (e.g. MARKET_CLOSED days) render a dashboard instead of KeyError-ing.
    latest = latest or {}
    run_kind = latest.get("run_kind", "FULL")
    latest_run = (latest.get("run_date_utc") or "—")[:10]
    fwd_days = latest.get("forward_days_accumulated", 0)
    state = latest.get("global_state", "INSUFFICIENT_EVIDENCE")
    halt = latest.get("halt_review_required", False)

    sharpe_target = cfg["min_evidence"]["daily_metrics_days"]
    maxdd_target = cfg["min_evidence"]["maxdd_days"]

    fp_status = latest.get("fingerprint_status", "UNKNOWN")
    fp_sealed = latest.get("fingerprint_hash_sealed") or ""
    fp_current = latest.get("fingerprint_hash_current") or ""
    broker_status = latest.get("broker_status", {"available": False, "reason": ""})

    lines: list[str] = [
        f"# MON001 · Operator Dashboard — {date.today().isoformat()}",
        "",
        f"_Auto-generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_",
        "",
    ]
    if run_kind == "MARKET_CLOSED":
        lines += [
            "> **MARKET_CLOSED**: metric engine skipped for a non-trading day. "
            "Fingerprint + ledger checks still ran; forward-day counters unchanged.",
            "",
        ]
    lines += [
        "## Summary",
        "",
        f"- **State**: `{state}`",
        f"- **HALT_REVIEW_REQUIRED**: `{halt}`",
        f"- **Forward boundary**: `{cfg['forward_boundary_asof']}`",
        f"- **Forward trading days accumulated**: {fwd_days}",
        f"- **Days until first Sharpe reading (T{sharpe_target})**: "
        f"{_remaining_days(fwd_days, sharpe_target)}",
        f"- **Days until first MaxDD reading (T{maxdd_target})**: "
        f"{_remaining_days(fwd_days, maxdd_target)}",
        f"- **Latest forward recommendation asof**: `{latest_asof}`",
        f"- **Latest monitoring run**: `{latest_run}`",
        "",
        "## Ledger health",
        "",
        f"- **Rows ingested**: {len(ledger_rows)}",
        f"- **Chain integrity**: `{integrity['ok']}`  ({integrity['reason']})",
        f"- **Duplicate rec_ids under same fingerprint**: "
        f"{len(ledger.duplicate_rec_ids())}",
        f"- **Forward boundary breach**: "
        f"{'YES — INVESTIGATE' if not integrity['ok'] and 'boundary' in integrity['reason'] else 'no'}",
        "",
        "## Baseline fingerprint",
        "",
        f"- **Status**: `{fp_status}`",
        f"- **Sealed hash**: `{fp_sealed[:16]}...`" if fp_sealed else "- **Sealed hash**: `—`",
        f"- **Current hash**: `{fp_current[:16]}...`" if fp_current else "- **Current hash**: `—`",
        "",
        "## Broker status",
        "",
        f"- **Available**: `{broker_status.get('available')}`",
        f"- **Reason**: {broker_status.get('reason', '')}",
        "",
        "## Active alerts (last 7 days, WARN or higher)",
        "",
    ]

    if not active_alerts:
        lines.append("_No active alerts._")
    else:
        lines.append("| Dimension | Severity | Consecutive | First seen | Reason |")
        lines.append("|---|:-:|:-:|:-:|---|")
        for a in active_alerts[-10:]:
            lines.append(
                f"| {a.get('dimension')} | `{a.get('severity')}` | "
                f"{a.get('consecutive_occurrences', 1)} | "
                f"{a.get('first_occurrence') or '—'} | {a.get('reason', '')} |")

    lines.extend([
        "",
        "## Metric evidence timeline",
        "",
    ])
    if latest and latest.get("metric_evidence"):
        lines.append("| Metric | Forward | Status | Sample | Minimum |")
        lines.append("|---|---:|:-:|---:|---:|")
        for m in latest["metric_evidence"]:
            lines.append(
                f"| {m['metric']} | {_fmt(m['forward_value'])} | "
                f"`{m['status']}` | {m['sample_size']} | {m['minimum_required']} |")

    lines.extend([
        "",
        "## Recent monitoring runs",
        "",
    ])
    files = sorted(reports_dir.glob("mon001_diagnostics_*.json"))[-5:]
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            lines.append(f"- `{p.name}` — state=`{d.get('global_state')}` "
                          f"halt=`{d.get('halt_review_required')}` "
                          f"recs={d.get('forward_recs_ingested')}")
        except Exception:
            lines.append(f"- `{p.name}` (unreadable)")

    lines.extend([
        "",
        "## Governance reminder",
        "",
        "- MON001 does NOT modify production.",
        "- HALT_REVIEW_REQUIRED is an operator-review signal only.",
        "- Do not tune strategy in response to drift alerts.",
        "- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.",
    ])

    return "\n".join(x for x in lines if x != "")


def main():
    dash = build_dashboard()
    out_path = HERE / "reports" / f"dashboard_{date.today().isoformat()}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dash, encoding="utf-8")
    print(f"MON001 dashboard -> {out_path}")


if __name__ == "__main__":
    main()
