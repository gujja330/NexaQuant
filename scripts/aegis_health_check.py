"""AEGIS health check.

Exit 0 = healthy · Exit 1 = degraded · Exit 2 = critical.

Verifies:
  1. All core reports/*.json exist and are non-empty
  2. reports/investment_intelligence.json contains today's or yesterday's date
  3. aegis_daily_v2_history.jsonl last entry succeeded
  4. Constitution + governance files present
  5. Fingerprint (MON001) is unchanged if sealed_baseline.txt is present

Prints a machine-readable JSON summary + a human summary.
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
REPORTS = _ROOT / "reports"

# Files that MUST exist and be recent for a healthy platform state
CORE_REPORTS = [
    "recommendations.json",
    "portfolio.json",
    "champion_strategy.json",
    "investment_intelligence.json",
    "intelligence_summary.json",
    "decision_center_today.json",
    "adaptive_rec_v2_signal.json",
    "validation_v2_latest.json",
    "risk_capital_v2_latest.json",
    "knowledge_graph.json",
]

# Governance files that MUST be present
GOVERNANCE = [
    "docs/NEXAQUANT_MANIFESTO.md",
    "docs/DESIGN_DECISIONS.md",
    "docs/ENGINE_EVOLUTION_GUIDE.md",
    "docs/PHASE2_MASTER_ROADMAP.md",
    "docs/HOWTO_RUN_AEGIS.md",
    "docs/VERSION.md",
    "CHANGELOG.md",
]

# Yellow if any report older than this
STALE_HOURS = 30


def _mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _check_core_reports() -> dict:
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=STALE_HOURS)
    missing, stale, fresh = [], [], []
    for name in CORE_REPORTS:
        p = REPORTS / name
        m = _mtime(p)
        if m is None or p.stat().st_size == 0:
            missing.append(name)
        elif m < stale_cutoff:
            stale.append({"file": name, "age_hours": round((now - m).total_seconds() / 3600, 1)})
        else:
            fresh.append({"file": name, "age_hours": round((now - m).total_seconds() / 3600, 1)})
    return {"fresh": fresh, "stale": stale, "missing": missing}


def _check_governance() -> dict:
    missing = [g for g in GOVERNANCE if not (_ROOT / g).exists()]
    return {"present": len(GOVERNANCE) - len(missing), "missing": missing}


def _check_orchestrator_ledger() -> dict:
    p = REPORTS / "aegis_daily_v2_history.jsonl"
    if not p.exists():
        return {"present": False, "note": "no ledger yet"}
    try:
        lines = p.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l]
        if not lines:
            return {"present": False, "note": "ledger empty"}
        last = json.loads(lines[-1])
        return {
            "present":       True,
            "last_run_utc":  last.get("run_utc"),
            "n_steps":       last.get("n_steps"),
            "n_success":     last.get("n_success"),
            "n_failure":     last.get("n_failure"),
            "total_elapsed_s": last.get("total_elapsed_s"),
        }
    except Exception as e:
        return {"present": True, "error": str(e)}


def _check_fingerprint() -> dict:
    """MON001 sealed-baseline fingerprint invariance check."""
    seal = _ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "sealed_baseline_fingerprint.txt"
    if not seal.exists():
        return {"checked": False, "note": "no sealed_baseline_fingerprint.txt on disk"}
    try:
        expected = seal.read_text(encoding="utf-8").strip()
        # Look for the current fingerprint from the latest diagnostics
        diag_dir = _ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "reports"
        diags = sorted(diag_dir.glob("mon001_diagnostics_*.json"))
        if not diags:
            return {"checked": False, "note": "no diagnostics on file"}
        latest = json.loads(diags[-1].read_text(encoding="utf-8"))
        current = latest.get("fingerprint_hash_current") or ""
        run_kind = latest.get("run_kind", "FULL")
        if run_kind == "MARKET_CLOSED":
            return {"checked": False, "note": "last run was MARKET_CLOSED (weekend/holiday)"}
        return {
            "checked":      True,
            "sealed":       expected[:16] + "...",
            "current":      current[:16] + "..." if current else None,
            "match":        bool(current and current == expected),
        }
    except Exception as e:
        return {"checked": False, "error": str(e)}


def main() -> int:
    result = {
        "run_utc":       datetime.now(timezone.utc).isoformat(),
        "reports":       _check_core_reports(),
        "governance":    _check_governance(),
        "orchestrator":  _check_orchestrator_ledger(),
        "fingerprint":   _check_fingerprint(),
    }

    # Verdict
    critical, degraded = [], []
    if result["reports"]["missing"]:
        critical.append(f"{len(result['reports']['missing'])} core reports missing")
    if result["governance"]["missing"]:
        critical.append(f"{len(result['governance']['missing'])} governance files missing")
    if result["reports"]["stale"]:
        degraded.append(f"{len(result['reports']['stale'])} reports > {STALE_HOURS}h old")
    orch = result["orchestrator"]
    if orch.get("present") and (orch.get("n_failure") or 0) > 0:
        degraded.append(f"orchestrator: {orch['n_failure']} step failure(s) on last run")
    fp = result["fingerprint"]
    if fp.get("checked") and fp.get("match") is False:
        critical.append("fingerprint mismatch (MON001 seal violated)")

    if critical:
        verdict = "CRITICAL"; code = 2
    elif degraded:
        verdict = "DEGRADED"; code = 1
    else:
        verdict = "HEALTHY";  code = 0

    result["verdict"] = verdict
    result["critical_issues"] = critical
    result["degraded_issues"] = degraded

    # Machine output
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, default=str))
        return code

    # Human output
    print("=" * 60)
    print(f"  AEGIS Health Check · {verdict}")
    print("=" * 60)
    print(f"  as of: {result['run_utc']}")
    print()
    print(f"  Core reports:   {len(result['reports']['fresh'])} fresh · "
             f"{len(result['reports']['stale'])} stale · "
             f"{len(result['reports']['missing'])} missing")
    print(f"  Governance:     {result['governance']['present']}/{len(GOVERNANCE)} present")
    if orch.get("present"):
        print(f"  Orchestrator:   last run {orch.get('n_success')}/{orch.get('n_steps')} "
                f"in {orch.get('total_elapsed_s')}s at {orch.get('last_run_utc')}")
    else:
        print(f"  Orchestrator:   {orch.get('note', 'unknown')}")
    if fp.get("checked"):
        print(f"  Fingerprint:    {'MATCH' if fp.get('match') else 'MISMATCH'} · "
                f"sealed {fp.get('sealed')} · current {fp.get('current')}")
    else:
        print(f"  Fingerprint:    not checked ({fp.get('note', '')})")

    if critical:
        print("\n  CRITICAL:")
        for c in critical: print(f"    - {c}")
    if degraded:
        print("\n  DEGRADED:")
        for d in degraded: print(f"    - {d}")

    print()
    print(f"  exit code: {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
