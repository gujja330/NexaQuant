"""AEGIS USA · Operational Hardening.

Verifies USA pipeline artefacts. Emits usa/reports/ops_check.json.
Exit 0 on HEALTHY/DEGRADED, 1 on CRITICAL.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_USA = Path(__file__).resolve().parents[1]
REPORTS = _USA / "reports"

REQUIRED = [
    "universe.json", "market_data_freshness.json",
    "recommendations.json", "investment_intelligence.json", "intelligence_summary.json",
    "intelligence_conflicts.json", "price_context.json",
    "validation_latest.json", "stock_validation.json",
    "risk_latest.json",
    "recommendation_lifecycle.json", "missed_opportunities.json", "recommendation_history.json",
    "winner_genome.json", "decision_attribution.json", "benchmark.json",
    "morning_latest.md", "morning_latest.html",
]

SCHEMAS = {
    "recommendations.json":         ["engine", "run_utc", "n_companies_evaluated", "recommendations"],
    "investment_intelligence.json": ["engine", "reports"],
    "benchmark.json":               ["engine", "version", "run_utc", "portfolio"],
    "decision_attribution.json":    ["engine", "version", "n_recommendations", "subsystem_weights", "per_recommendation"],
    "recommendation_lifecycle.json": ["engine", "version", "n_total", "by_ticker"],
    "recommendation_history.json":  ["market", "n_tickers", "n_days_archived", "tickers"],
    "risk_latest.json":             ["engine", "run_utc", "sizing", "portfolio_risk"],
    "price_context.json":           ["engine", "n_tickers", "tickers"],
    "winner_genome.json":           ["engine", "version", "mode"],
}


def main() -> int:
    print("=" * 70)
    print("  AEGIS USA · Ops Check")
    print("=" * 70)

    present, missing, invalid = [], [], []
    total_bytes = 0
    for name in REQUIRED:
        p = REPORTS / name
        if not p.exists():
            missing.append(name); continue
        total_bytes += p.stat().st_size
        if name.endswith(".json"):
            try:
                json.loads(p.read_text(encoding="utf-8"))
                present.append(name)
            except Exception as e:
                invalid.append({"name": name, "error": str(e)[:100]})
        else:
            present.append(name)

    schema_failures = []
    for name, keys in SCHEMAS.items():
        p = REPORTS / name
        if not p.exists(): continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            miss = [k for k in keys if k not in obj]
            if miss:
                schema_failures.append({"name": name, "missing_keys": miss})
        except Exception:
            pass

    if missing or invalid:
        verdict = "CRITICAL" if len(missing) > 3 or invalid else "DEGRADED"
    elif schema_failures:
        verdict = "DEGRADED"
    else:
        verdict = "HEALTHY"

    result = {
        "engine":     "usa_ops_check",
        "version":    "v1.0",
        "market":     "USA",
        "run_utc":    datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "verdict":    verdict,
        "artifacts":  {
            "n_required":   len(REQUIRED),
            "n_present":    len(present),
            "n_missing":    len(missing),
            "n_invalid":    len(invalid),
            "missing":      missing,
            "invalid":      invalid,
            "total_bytes":  total_bytes,
        },
        "schemas":    {
            "n_schemas":  len(SCHEMAS),
            "n_pass":     len(SCHEMAS) - len(schema_failures),
            "n_fail":     len(schema_failures),
            "failures":   schema_failures,
        },
    }
    (REPORTS / "ops_check.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print(f"  ARTIFACTS   {len(present)}/{len(REQUIRED)} present  ·  {len(invalid)} invalid  ({total_bytes/1024:.1f} KB)")
    if missing: print(f"    missing: {missing}")
    print(f"  SCHEMAS     {len(SCHEMAS) - len(schema_failures)}/{len(SCHEMAS)} pass")
    for f in schema_failures: print(f"    FAIL {f['name']}: {f['missing_keys']}")
    print(f"  VERDICT     {verdict}")
    return 0 if verdict != "CRITICAL" else 1


if __name__ == "__main__":
    sys.exit(main())
