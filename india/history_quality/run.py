"""AEGIS India · History Quality Validation runner (Sprint B0)."""
from __future__ import annotations
import io
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.history_quality import run_quality_check, ENGINE_ID, ENGINE_VERSION
from backend.feature_store import schema_fingerprint
from backend.model_registry.registry import stamp, register_model, ModelStatus

OUT = _ROOT / "reports" / "history_quality_report.json"


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"[AEGIS India · History Quality Validation · {now.isoformat(timespec='seconds')}]")

    register_model(_ROOT,
        model_id=ENGINE_ID, engine="history_quality",
        market="india", version=ENGINE_VERSION,
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by india/history_quality on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, ENGINE_ID)

    report = run_quality_check(repo_root=_ROOT, market="india")
    payload = {
        "engine": report.engine, "version": report.version,
        "market": report.market, "run_utc": report.run_utc,
        "verdict": report.verdict,
        "overall_quality_score": report.overall_quality_score,
        "counts": {
            "PASS": report.n_pass, "WARN": report.n_warn,
            "FAIL": report.n_fail, "NOT_APPLICABLE": report.n_not_applicable,
        },
        "n_families_checked": report.n_families_checked,
        "per_family": [asdict(r) for r in report.per_family],
        "corporate_action_flags": report.corporate_action_flags,
        "notes": report.notes,
        "model_stamp": model_stamp,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"  verdict:     {report.verdict}")
    print(f"  score:       {report.overall_quality_score}/100")
    print(f"  families:    PASS={report.n_pass} WARN={report.n_warn} FAIL={report.n_fail} N/A={report.n_not_applicable}")
    for r in report.per_family:
        marker = {"PASS": "OK ", "WARN": "WRN", "FAIL": "FAIL", "NOT_APPLICABLE": "N/A"}.get(r.status, "?  ")
        print(f"    [{marker}] {r.family:30s} rows={r.n_rows:>6}  score={r.quality_score}/100  {r.date_range or ''}")
    if report.corporate_action_flags:
        print(f"  CA flags:    {len(report.corporate_action_flags)}")
    print(f"  wrote {OUT.relative_to(_ROOT)}")
    return 0 if report.verdict != "NEEDS_REPAIR" else 1


if __name__ == "__main__":
    sys.exit(main())
