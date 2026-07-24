"""AEGIS USA · History Quality Validation runner (Sprint B0).

Also builds the global comparison artifact at reports/global/history_quality_comparison.json
(runs after both India + USA outputs exist)."""
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

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.history_quality import run_quality_check, ENGINE_ID, ENGINE_VERSION, build_comparison
from backend.feature_store import schema_fingerprint
from backend.model_registry.registry import stamp, register_model, ModelStatus

OUT = _ROOT / "usa" / "reports" / "history_quality_report.json"
GLOBAL_OUT = _ROOT / "reports" / "global" / "history_quality_comparison.json"


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"[AEGIS USA · History Quality Validation · {now.isoformat(timespec='seconds')}]")

    register_model(_ROOT,
        model_id=ENGINE_ID, engine="history_quality",
        market="usa", version=ENGINE_VERSION,
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by usa/history_quality on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, ENGINE_ID)

    usa_report = run_quality_check(repo_root=_ROOT, market="usa")
    payload = {
        "engine": usa_report.engine, "version": usa_report.version,
        "market": usa_report.market, "run_utc": usa_report.run_utc,
        "verdict": usa_report.verdict,
        "overall_quality_score": usa_report.overall_quality_score,
        "counts": {
            "PASS": usa_report.n_pass, "WARN": usa_report.n_warn,
            "FAIL": usa_report.n_fail, "NOT_APPLICABLE": usa_report.n_not_applicable,
        },
        "n_families_checked": usa_report.n_families_checked,
        "per_family": [asdict(r) for r in usa_report.per_family],
        "corporate_action_flags": usa_report.corporate_action_flags,
        "notes": usa_report.notes,
        "model_stamp": model_stamp,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"  verdict:     {usa_report.verdict}")
    print(f"  score:       {usa_report.overall_quality_score}/100")
    print(f"  families:    PASS={usa_report.n_pass} WARN={usa_report.n_warn} FAIL={usa_report.n_fail} N/A={usa_report.n_not_applicable}")
    for r in usa_report.per_family:
        marker = {"PASS": "OK ", "WARN": "WRN", "FAIL": "FAIL", "NOT_APPLICABLE": "N/A"}.get(r.status, "?  ")
        print(f"    [{marker}] {r.family:30s} rows={r.n_rows:>6}  score={r.quality_score}/100  {r.date_range or ''}")
    print(f"  wrote {OUT.relative_to(_ROOT)}")

    # Build global comparison if India report exists
    india_out = _ROOT / "reports" / "history_quality_report.json"
    if india_out.exists():
        india_data = json.loads(india_out.read_text(encoding="utf-8"))
        # Rehydrate India as a QualityReport for comparison; keep it lightweight — pass a
        # minimal object via dict-only compare.
        from backend.history_quality.types import QualityReport, FamilyCheckResult
        india_report = QualityReport(
            engine=india_data.get("engine", "aegis.history_quality.v1"),
            version=india_data.get("version", "1.0.0"),
            market="india",
            run_utc=india_data.get("run_utc", ""),
            verdict=india_data.get("verdict", ""),
            n_families_checked=india_data.get("n_families_checked", 0),
            n_pass=india_data.get("counts", {}).get("PASS", 0),
            n_warn=india_data.get("counts", {}).get("WARN", 0),
            n_fail=india_data.get("counts", {}).get("FAIL", 0),
            n_not_applicable=india_data.get("counts", {}).get("NOT_APPLICABLE", 0),
            overall_quality_score=india_data.get("overall_quality_score", 0),
            per_family=[FamilyCheckResult(**{
                k: v for k, v in r.items()
                if k in FamilyCheckResult.__dataclass_fields__
            }) for r in india_data.get("per_family", [])],
            corporate_action_flags=india_data.get("corporate_action_flags", []),
            notes=india_data.get("notes", []),
        )
        build_comparison(india=india_report, usa=usa_report, output_path=GLOBAL_OUT)
        print(f"  wrote {GLOBAL_OUT.relative_to(_ROOT)}")
    else:
        print(f"  (india report not present at {india_out.relative_to(_ROOT)} — global comparison skipped)")

    return 0 if usa_report.verdict != "NEEDS_REPAIR" else 1


if __name__ == "__main__":
    sys.exit(main())
