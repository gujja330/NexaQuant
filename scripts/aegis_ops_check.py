"""AEGIS Operational Hardening · unified daily check.

Runs at the tail of every pipeline execution and on every CI build.
Verifies:

  1. Artifact Completeness  — every declared output exists + valid JSON
  2. JSON Schema Validation — minimal schema per artifact (required keys +
                              array shapes), no silent format drift
  3. Fingerprint Sentinel   — MON001 sealed-baseline fingerprint unchanged
  4. Health Rollup          — orchestrator step outcomes from history ledger
  5. Ops Verdict            — HEALTHY / DEGRADED / CRITICAL

Emits reports/ops_check.json. Exit 0 if HEALTHY/DEGRADED, 1 if CRITICAL.

Post-LOCK operational hardening. No new engine — just verification.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
REPORTS = _ROOT / "reports"


# ── 1. Artifact completeness ──────────────────────────────────────

# Every artifact the SPA + pipeline REQUIRE. Anything missing = degraded.
REQUIRED_ARTIFACTS = [
    "backend_validation_summary.json",   # Sprint 1 addition
    "recommendations.json",
    "investment_intelligence.json",
    "intelligence_summary.json",
    "risk_capital_v2_latest.json",
    "validation_v2_latest.json",
    "stock_validation.json",
    "price_context.json",
    "global_context.json",
    "champion_strategy.json",
    "confidence_calibration.json",
    "decision_center_today.json",
    "decision_center_notifications.json",
    "recommendation_dna_feedback.json",
    "knowledge_graph.json",
    "winner_genome.json",
    "decision_attribution.json",
    "benchmark.json",
    "recommendation_lifecycle.json",
    "missed_opportunities.json",
    "recommendation_history.json",
    "morning_latest.md",
    "morning_latest.html",
]


def check_artifacts() -> dict:
    present, missing, invalid = [], [], []
    total_bytes = 0
    for name in REQUIRED_ARTIFACTS:
        p = REPORTS / name
        if not p.exists():
            missing.append(name); continue
        b = p.stat().st_size
        total_bytes += b
        if name.endswith(".json"):
            try:
                json.loads(p.read_text(encoding="utf-8"))
                present.append({"name": name, "bytes": b, "ok": True})
            except Exception as e:
                invalid.append({"name": name, "bytes": b, "error": str(e)[:120]})
        else:
            present.append({"name": name, "bytes": b, "ok": True})
    return {
        "n_required":  len(REQUIRED_ARTIFACTS),
        "n_present":   len(present),
        "n_missing":   len(missing),
        "n_invalid":   len(invalid),
        "total_bytes": total_bytes,
        "missing":     missing,
        "invalid":     invalid,
    }


# ── 2. JSON schema validation ──────────────────────────────────────

# Minimal schemas — required top-level keys + expected shape of critical arrays.
# Format: {file → {"required_keys": [...], "array_of_dicts": {key: [required_dict_keys, ...]}}}
SCHEMAS: dict[str, dict] = {
    "recommendations.json": {
        "required_keys": ["run_utc", "n_companies_evaluated", "n_currently_held", "recommendations"],
        "array_of_dicts": {"recommendations": ["ticker", "sector", "recommendation", "confidence", "entry_exit"]},
    },
    "investment_intelligence.json": {
        "required_keys": ["reports"],
        "array_of_dicts": {"reports": ["ticker", "intelligence_score"]},
    },
    "benchmark.json": {
        "required_keys": ["available", "engine", "version", "run_utc"],
        # portfolio + per_ticker are conditional on available=True
    },
    "decision_attribution.json": {
        "required_keys": ["engine", "version", "n_recommendations", "subsystem_weights",
                           "per_recommendation", "subsystem_accuracy"],
    },
    "winner_genome.json": {
        "required_keys": ["engine", "version", "mode", "signatures", "matches"],
    },
    "recommendation_lifecycle.json": {
        "required_keys": ["engine", "version", "n_total", "by_state", "by_ticker"],
    },
    "missed_opportunities.json": {
        "required_keys": ["engine", "version", "n_days_scanned", "n_events"],
    },
    "recommendation_history.json": {
        "required_keys": ["n_tickers", "n_days_archived", "tickers"],
    },
    "price_context.json": {
        "required_keys": ["n_tickers", "n_available", "tickers"],
    },
    "stock_validation.json": {
        "required_keys": ["n_tickers", "n_with_history", "tickers"],
    },
    "decision_center_today.json": {
        "required_keys": ["run_utc", "first_run"],
    },
    "risk_capital_v2_latest.json": {
        "required_keys": ["run_utc", "sizing"],
        "array_of_dicts": {"sizing": ["ticker", "target_weight"]},
    },
    "champion_strategy.json": {
        "required_keys": ["champion"],
    },
    "global_context.json": {
        "required_keys": ["asof_utc", "composites"],
    },
}


def _validate_one(name: str, schema: dict) -> dict:
    p = REPORTS / name
    if not p.exists():
        return {"name": name, "ok": False, "reason": "missing"}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"name": name, "ok": False, "reason": f"invalid JSON: {str(e)[:100]}"}
    missing_keys = [k for k in schema.get("required_keys", []) if k not in obj]
    if missing_keys:
        return {"name": name, "ok": False, "reason": f"missing keys: {missing_keys}"}
    # Array-of-dicts check
    for arr_key, required_dict_keys in (schema.get("array_of_dicts") or {}).items():
        arr = obj.get(arr_key)
        if not isinstance(arr, list):
            return {"name": name, "ok": False, "reason": f"'{arr_key}' is not a list"}
        if arr:
            sample = arr[0]
            if not isinstance(sample, dict):
                return {"name": name, "ok": False, "reason": f"'{arr_key}[0]' is not a dict"}
            miss = [k for k in required_dict_keys if k not in sample]
            if miss:
                return {"name": name, "ok": False,
                        "reason": f"'{arr_key}[0]' missing keys: {miss}"}
    return {"name": name, "ok": True}


def check_schemas() -> dict:
    results = [_validate_one(name, schema) for name, schema in SCHEMAS.items()]
    failed = [r for r in results if not r["ok"]]
    return {
        "n_schemas":   len(SCHEMAS),
        "n_pass":      len(results) - len(failed),
        "n_fail":      len(failed),
        "failures":    failed,
    }


# ── 3. Fingerprint sentinel ───────────────────────────────────────

def check_fingerprint() -> dict:
    seal = _ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "sealed_baseline_fingerprint.txt"
    if not seal.exists():
        return {"checked": False, "reason": "sealed_baseline_fingerprint.txt not on disk"}
    expected = seal.read_text(encoding="utf-8").strip().split()[0][:16]
    # Look up current fingerprint from latest diagnostics
    diag_dir = _ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "reports"
    if not diag_dir.exists():
        return {"checked": False, "reason": "MON001 reports dir missing", "expected": expected}
    diags = sorted(diag_dir.glob("mon001_diagnostics_*.json"))
    if not diags:
        return {"checked": False, "reason": "no MON001 diagnostics on disk", "expected": expected}
    latest = json.loads(diags[-1].read_text(encoding="utf-8"))
    current = (latest.get("fingerprint_hash_current") or "").strip()[:16]
    match = (current == expected) if (current and expected) else False
    return {
        "checked":  True,
        "expected": expected,
        "current":  current,
        "match":    match,
        "verdict":  "OK" if match else "DRIFT",
    }


# ── 4. Health rollup from orchestrator history ────────────────────

def check_health() -> dict:
    ledger = REPORTS / "aegis_daily_v2_history.jsonl"
    if not ledger.exists():
        return {"checked": False, "reason": "no history ledger"}
    lines = [ln.strip() for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return {"checked": False, "reason": "empty ledger"}
    # Most recent run
    try:
        latest = json.loads(lines[-1])
    except Exception:
        return {"checked": False, "reason": "unparseable ledger tail"}
    steps = latest.get("steps") or latest.get("results") or []
    n_ok    = sum(1 for s in steps if s.get("verdict") in ("OK", "SUCCESS", "SKIPPED_OPTIONAL"))
    n_fail  = sum(1 for s in steps if s.get("verdict") not in ("OK", "SUCCESS", "SKIPPED_OPTIONAL"))
    return {
        "checked":      True,
        "run_utc":      latest.get("run_utc"),
        "n_steps":      len(steps),
        "n_ok":         n_ok,
        "n_fail":       n_fail,
        "elapsed_s":    latest.get("elapsed_s") or latest.get("total_elapsed_s"),
    }


# ── 5. Rollup verdict ─────────────────────────────────────────────

def check_backend_validation() -> dict:
    """Read reports/backend_validation_summary.json and roll into ops verdict."""
    p = REPORTS / "backend_validation_summary.json"
    if not p.exists():
        return {"checked": False, "reason": "backend_validation_summary.json missing"}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"checked": False, "reason": f"unparseable: {e}"}
    return {
        "checked":       True,
        "market":        s.get("market"),
        "verdict":       s.get("verdict"),
        "confidence":    s.get("confidence"),
        "n_datasets":    s.get("n_datasets"),
        "counts":        s.get("counts"),
        "n_top_issues":  len(s.get("top_issues") or []),
        "run_utc":       s.get("run_utc"),
    }


def build_verdict(artifacts: dict, schemas: dict, fingerprint: dict, health: dict,
                    backend: dict | None = None) -> str:
    critical = []
    if artifacts["n_missing"] > 3:
        critical.append(f"{artifacts['n_missing']} artifacts missing")
    if artifacts["n_invalid"] > 0:
        critical.append(f"{artifacts['n_invalid']} artifacts have invalid JSON")
    if schemas["n_fail"] > 3:
        critical.append(f"{schemas['n_fail']} schema failures")
    if fingerprint.get("checked") and not fingerprint.get("match"):
        critical.append("MON001 fingerprint DRIFT — architecture seal violated")
    if health.get("checked") and health.get("n_fail", 0) > 2:
        critical.append(f"{health['n_fail']} orchestrator steps failed")

    degraded = []
    if 0 < artifacts["n_missing"] <= 3:
        degraded.append(f"{artifacts['n_missing']} artifact(s) missing")
    if 0 < schemas["n_fail"] <= 3:
        degraded.append(f"{schemas['n_fail']} schema warning(s)")
    if not fingerprint.get("checked"):
        degraded.append("fingerprint not verifiable")
    if health.get("checked") and 0 < health.get("n_fail", 0) <= 2:
        degraded.append(f"{health['n_fail']} step warning(s)")

    # Backend validation rollup (Sprint 1)
    if backend and backend.get("checked"):
        bv = backend.get("verdict")
        if bv == "FAIL":
            critical.append(f"backend validation FAIL ({backend.get('counts', {}).get('FAIL', 0)} datasets)")
        elif bv == "WARNING":
            degraded.append("backend validation WARNING")

    if critical: return "CRITICAL"
    if degraded: return "DEGRADED"
    return "HEALTHY"


def main() -> int:
    print("=" * 68)
    print("  AEGIS OPS CHECK · artifact + schema + fingerprint + health")
    print("=" * 68)

    artifacts = check_artifacts()
    schemas   = check_schemas()
    fingerprint = check_fingerprint()
    health    = check_health()
    backend   = check_backend_validation()
    verdict   = build_verdict(artifacts, schemas, fingerprint, health, backend)

    result = {
        "engine":    "ops_check",
        "version":   "v1.1",
        "run_utc":   datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "verdict":   verdict,
        "artifacts": artifacts,
        "schemas":   schemas,
        "fingerprint": fingerprint,
        "health":    health,
        "backend_validation": backend,
    }

    print(f"\n  ARTIFACTS   {artifacts['n_present']}/{artifacts['n_required']} present"
          f" · {artifacts['n_invalid']} invalid  ({artifacts['total_bytes']/1024:.1f} KB total)")
    if artifacts["missing"]:
        print(f"    missing: {artifacts['missing']}")
    if artifacts["invalid"]:
        print(f"    invalid: {[i['name'] for i in artifacts['invalid']]}")

    print(f"\n  SCHEMAS     {schemas['n_pass']}/{schemas['n_schemas']} pass")
    if schemas["failures"]:
        for f in schemas["failures"]:
            print(f"    FAIL {f['name']}: {f['reason']}")

    print(f"\n  FINGERPRINT ", end="")
    if fingerprint.get("checked"):
        print(f"{fingerprint['verdict']}  expected={fingerprint['expected']}  current={fingerprint['current']}")
    else:
        print(f"not checked ({fingerprint.get('reason')})")

    print(f"\n  HEALTH      ", end="")
    if health.get("checked"):
        print(f"{health['n_ok']}/{health['n_steps']} steps ok  elapsed={health.get('elapsed_s','—')}s")
    else:
        print(f"not checked ({health.get('reason')})")

    print(f"\n  BACKEND    ", end="")
    if backend.get("checked"):
        print(f"{backend['verdict']}  confidence={backend.get('confidence', 0):.3f}  "
              f"{backend.get('counts', {}).get('PASS', 0)}/{backend.get('n_datasets', 0)} datasets pass")
    else:
        print(f"not checked ({backend.get('reason')})")

    print(f"\n  VERDICT     {verdict}")

    (REPORTS / "ops_check.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  written: reports/ops_check.json")
    return 0 if verdict != "CRITICAL" else 1


if __name__ == "__main__":
    sys.exit(main())
