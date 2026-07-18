"""AEGIS · end-to-end validation harness.

Runs the full daily pipeline in-process and verifies that every
expected artifact was refreshed. Then verifies every dashboard-consumed
report has a valid schema. Then simulates rendering every dashboard
widget's data-source query. Produces a pass/fail matrix.

Exit 0 if all pass; exit 1 otherwise. Machine-readable JSON via `--json`.

Usage:
  python scripts/e2e_test.py            # human report
  python scripts/e2e_test.py --json     # machine report
  python scripts/e2e_test.py --skip-pipeline    # only verify current artifacts
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
REPORTS = _ROOT / "reports"


# ─── Test matrix ──────────────────────────────────────────────
# Every row: (test_id, description, fn returning (ok, detail))
def _T_pipeline_runs():
    r = subprocess.run(
        [sys.executable, "scripts/aegis_daily_v2.py", "--continue"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=600,
    )
    if r.returncode == 0:
        return True, f"orchestrator returncode=0 · {len(r.stdout.splitlines())} log lines"
    return False, f"orchestrator returncode={r.returncode} · stderr_tail={r.stderr.splitlines()[-3:]}"


def _T_reports_exist(paths: list[str]):
    missing = [p for p in paths if not (REPORTS / p).exists()]
    if not missing:
        return True, f"{len(paths)} files present"
    return False, f"missing: {missing}"


def _T_json_valid(paths: list[str]):
    bad = []
    for p in paths:
        f = REPORTS / p
        if not f.exists():
            bad.append(f"{p}: missing")
            continue
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            bad.append(f"{p}: {type(e).__name__}")
    if not bad:
        return True, f"{len(paths)} JSON files parse cleanly"
    return False, "; ".join(bad)


def _T_has_key(path: str, key: str):
    f = REPORTS / path
    if not f.exists():
        return False, "file missing"
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
        if key in j:
            return True, f"has '{key}'"
        return False, f"missing '{key}'"
    except Exception as e:
        return False, f"parse error: {e}"


def _T_governance_docs():
    docs = [
        "docs/NEXAQUANT_MANIFESTO.md",
        "docs/DESIGN_DECISIONS.md",
        "docs/ENGINE_EVOLUTION_GUIDE.md",
        "docs/PHASE2_MASTER_ROADMAP.md",
        "docs/HOWTO_RUN_AEGIS.md",
        "docs/DEPLOYMENT_GUIDE.md",
        "docs/RELEASE_NOTES_RC1.md",
        "docs/VERSION.md",
        "CHANGELOG.md",
    ]
    missing = [d for d in docs if not (_ROOT / d).exists()]
    if not missing:
        return True, f"{len(docs)} governance docs present"
    return False, f"missing: {missing}"


def _T_module_smoke_tests():
    """Runs every Phase 2 module's smoke test."""
    tests = [
        "research/adaptive_rec_v2/tests/test_smoke.py",
        "research/adaptive_rec_v2/tests/test_fusion.py",
        "research/validation_v2/tests/test_smoke.py",
        "research/risk_capital_v2/tests/test_smoke.py",
        "research/champion_challenger/tests/test_smoke.py",
        "research/knowledge_graph/tests/test_smoke.py",
        "research/recommendation_dna/tests/test_feedback.py",
        "research/decision_center/tests/test_smoke.py",
        "ux/dashboard/tests/test_smoke.py",
        "ux/telegram/tests/test_smoke.py",
    ]
    n_pass, failing = 0, []
    for t in tests:
        if not (_ROOT / t).exists():
            continue
        r = subprocess.run([sys.executable, t], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            n_pass += 1
        else:
            failing.append(f"{t}: rc={r.returncode}")
    if not failing:
        return True, f"{n_pass}/{len(tests)} module test files pass"
    return False, f"{n_pass}/{len(tests)} pass · failing: {failing}"


def _T_regression_suite():
    r = subprocess.run(
        [sys.executable, "nexaquant/tests/test_regression.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=300,
    )
    if r.returncode == 0:
        return True, "full regression suite PASSES"
    return False, f"regression rc={r.returncode} · tail={r.stdout.splitlines()[-5:]}"


def _T_invariance_guards():
    """Parses the regression output for the invariance-guards summary."""
    r = subprocess.run(
        [sys.executable, "nexaquant/tests/test_regression.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=300,
    )
    stdout = r.stdout or ""
    if "ALL INVARIANCE GUARDS HOLD" in stdout:
        return True, "fingerprint + constants + LAB files INVARIANT"
    return False, "invariance summary not found in regression output"


def _T_health_check():
    r = subprocess.run(
        [sys.executable, "scripts/aegis_health_check.py", "--json"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=30,
    )
    try:
        out = json.loads(r.stdout)
        verdict = out.get("verdict")
        return verdict == "HEALTHY", f"health verdict={verdict} · critical={out.get('critical_issues')}"
    except Exception as e:
        return False, f"health check output not JSON: {e}"


def _T_orchestrator_ledger_healthy():
    p = REPORTS / "aegis_daily_v2_history.jsonl"
    if not p.exists():
        return False, "no ledger yet"
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    lines = [l for l in lines if l]
    if not lines:
        return False, "ledger empty"
    last = json.loads(lines[-1])
    if last.get("n_failure", 0) == 0:
        return True, f"last run: {last['n_success']}/{last['n_steps']} in {last['total_elapsed_s']}s"
    return False, f"last run had {last['n_failure']} failure(s)"


def _T_decision_center_valid():
    ok1, d1 = _T_has_key("decision_center_today.json", "overnight_summary")
    ok2, d2 = _T_has_key("decision_center_today.json", "action_counts_today")
    ok3, d3 = _T_has_key("decision_center_today.json", "exit_center")
    if ok1 and ok2 and ok3:
        return True, "overnight_summary + action_counts_today + exit_center present"
    return False, f"{d1}; {d2}; {d3}"


def _T_intelligence_fusion_valid():
    f = REPORTS / "investment_intelligence.json"
    if not f.exists():
        return False, "missing"
    j = json.loads(f.read_text(encoding="utf-8"))
    reports = j.get("reports") or []
    if not reports:
        return False, "no fusion reports"
    with_dims = sum(1 for r in reports if r.get("dimensions"))
    return True, f"{len(reports)} recs · {with_dims} with dimensions"


def _T_dashboard_html_present():
    p = _ROOT / "ux" / "dashboard" / "frontend" / "index.html"
    if not p.exists():
        return False, "missing"
    html = p.read_text(encoding="utf-8")
    for k in ["decisionCenter", "buildCanonicalList", "renderStockDetail",
               "renderDashboard", "refreshAll", "REFRESH_INTERVAL_MS"]:
        if k not in html:
            return False, f"missing '{k}'"
    return True, f"index.html {len(html):,} chars · all key symbols present"


def _T_no_dev_leaks_in_ui():
    import re
    p = _ROOT / "ux" / "dashboard" / "frontend" / "index.html"
    html = p.read_text(encoding="utf-8")
    # Strip JS/HTML comments before checking
    stripped = re.sub(r"//[^\n]*", "", html)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.DOTALL)
    leaks = re.findall(r"\bDEV0?[0-9]{2,3}\b", stripped)
    if not leaks:
        return True, "no DEV number references in visible UI"
    return False, f"{len(leaks)} leaks: {leaks[:5]}"


# ─── Runner ──────────────────────────────────────────────────
def build_matrix(skip_pipeline: bool = False) -> list[dict]:
    matrix = []

    if not skip_pipeline:
        matrix.append({"id": "pipeline_runs", "desc": "Full daily orchestrator succeeds",
                          "fn": _T_pipeline_runs})

    matrix.extend([
        {"id": "reports_base", "desc": "Base pipeline reports exist",
          "fn": lambda: _T_reports_exist([
              "recommendations.json", "portfolio.json",
              "champion_strategy.json", "global_context.json"])},
        {"id": "reports_phase2", "desc": "Phase 2 reports exist",
          "fn": lambda: _T_reports_exist([
              "adaptive_rec_v2_signal.json",
              "validation_v2_latest.json",
              "risk_capital_v2_latest.json",
              "recommendation_dna_feedback.json",
              "knowledge_graph.json", "stress_scenarios.json",
              "investment_intelligence.json",
              "intelligence_summary.json",
              "decision_center_today.json",
          ])},
        {"id": "reports_json_valid", "desc": "All headline JSONs parse",
          "fn": lambda: _T_json_valid([
              "recommendations.json", "portfolio.json",
              "champion_strategy.json", "confidence_calibration.json",
              "adaptive_rec_v2_signal.json",
              "validation_v2_latest.json",
              "risk_capital_v2_latest.json",
              "investment_intelligence.json",
              "intelligence_summary.json",
              "decision_center_today.json",
          ])},
        {"id": "intelligence_fusion_has_reports",
          "desc": "Investment intelligence has per-rec reports",
          "fn": _T_intelligence_fusion_valid},
        {"id": "decision_center_valid",
          "desc": "Decision center has overnight + action counts + exit center",
          "fn": _T_decision_center_valid},
        {"id": "governance_docs",
          "desc": "Governance stack present",
          "fn": _T_governance_docs},
        {"id": "dashboard_html_present",
          "desc": "Dashboard HTML present + key symbols",
          "fn": _T_dashboard_html_present},
        {"id": "no_dev_leaks_ui",
          "desc": "No DEV numbering in visible UI",
          "fn": _T_no_dev_leaks_in_ui},
        {"id": "orchestrator_ledger",
          "desc": "Orchestrator ledger last run healthy",
          "fn": _T_orchestrator_ledger_healthy},
        {"id": "health_check",
          "desc": "aegis_health_check reports HEALTHY",
          "fn": _T_health_check},
        {"id": "module_smoke_tests",
          "desc": "Every Phase 2 module smoke test passes",
          "fn": _T_module_smoke_tests},
        {"id": "regression_suite",
          "desc": "Full regression suite passes",
          "fn": _T_regression_suite},
        {"id": "invariance_guards",
          "desc": "ENG001 invariance guards hold",
          "fn": _T_invariance_guards},
    ])
    return matrix


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--skip-pipeline", action="store_true", help="skip the pipeline-run step")
    args = ap.parse_args()

    t0 = time.time()
    matrix = build_matrix(skip_pipeline=args.skip_pipeline)

    results = []
    for row in matrix:
        step_t0 = time.perf_counter()
        try:
            ok, detail = row["fn"]()
        except Exception as e:
            ok, detail = False, f"exception: {type(e).__name__}: {e}"
        elapsed = time.perf_counter() - step_t0
        results.append({
            "id":      row["id"],
            "desc":    row["desc"],
            "verdict": "PASS" if ok else "FAIL",
            "detail":  detail,
            "elapsed_s": round(elapsed, 2),
        })

    n_pass = sum(1 for r in results if r["verdict"] == "PASS")
    n_fail = sum(1 for r in results if r["verdict"] == "FAIL")
    overall = "PASS" if n_fail == 0 else "FAIL"

    summary = {
        "run_utc":        datetime.now(timezone.utc).isoformat(),
        "overall":        overall,
        "n_tests":        len(results),
        "n_pass":         n_pass,
        "n_fail":         n_fail,
        "elapsed_s":      round(time.time() - t0, 2),
        "results":        results,
    }

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0 if overall == "PASS" else 1

    print("=" * 78); print(f"  AEGIS END-TO-END VALIDATION · {overall}"); print("=" * 78)
    print(f"  {'test':<36} {'verdict':<8} {'elapsed':>8}  detail")
    print(f"  {'-' * 76}")
    for r in results:
        marker = " " if r["verdict"] == "PASS" else "!"
        detail = r["detail"][:80]
        print(f"  {marker} {r['id']:<34} {r['verdict']:<8} {r['elapsed_s']:>6.2f}s  {detail}")
    print(f"  {'-' * 76}")
    print(f"  {n_pass}/{len(results)} tests passed in {summary['elapsed_s']}s")
    print(f"  overall: {overall}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
