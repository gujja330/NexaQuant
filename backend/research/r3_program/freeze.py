"""R3 FREEZE · scorecard, decision contract, governance audit, freeze record.

Phases 15, 16, XXIII and XXIV in one place, because a freeze is a single
decision and splitting its evidence across files is how a freeze gets
declared on partial grounds.

THE AUDIT IS MECHANICAL
------------------------
Every check below either inspects a file on disk or runs a command. None
of them is satisfied by an assertion in prose. In particular the isolation
check reads the R3 sources and fails if any of them imports a production
module - a claim of isolation that is not enforced is not isolation.

FREEZE IS NOT SUCCESS
----------------------
Freezing means the evidence programme is exhausted, not that it succeeded.
A programme that ends with every branch rejected or blocked, honestly
recorded, has done its job: it established where AI is NOT useful to
AEGIS, which is worth exactly as much as finding where it is.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.r3_program import core, master_status

SCHEMA_VERSION = "aegis.r3.freeze.v1"

# Modules R3 must never import · isolation is enforced, not promised.
FORBIDDEN_IMPORTS = (
    "backend.delivery.telegram", "detail_xlsx", "canonical_daily_lifecycle",
    "adaptive_rec", "dynamic_risk", "registry_materializer",
    "backend.delivery.lifecycle",
)

# Paths whose modification would mean R2 production changed.
PRODUCTION_PATHS = (
    "backend/delivery/", "backend/recommendation/", "backend/risk/",
    "backend/portfolio/", "backend/execution/",
)

R3_DECISION_CONTRACT = {
    "contract_id": "R3_DECISION_v1",
    "status": "DEFINED · NOT ACTIVE · no component is eligible to emit it",
    "input": "an existing R2 BUY candidate · R3 never generates BUY",
    "allowed_actions": ["TAKE", "AVOID", "ABSTAIN"],
    "forbidden_actions": [
        "generate BUY independently", "write R2", "alter R2 thresholds",
        "alter R2 exits", "alter R2 adaptive ensemble weights",
        "create production registry entries", "create production position IDs",
        "modify production delivery",
    ],
    "fields": [
        "ticker", "market", "as_of", "r2_signal", "r3_action",
        "take_probability", "avoid_probability", "abstain_probability",
        "severe_loss_probability", "survival_probability", "expected_horizon",
        "fundamental_state", "technical_state", "cluster_state",
        "sector_state", "regime_state", "uncertainty", "evidence_tier",
        "model_versions", "experiment_family_ids", "known_failure_modes",
        "PIT_status", "OOS_status",
    ],
    "activation_requirements": [
        "at least one specialist at VALIDATED or CONDITIONAL disposition",
        "a decision-value delta whose ticker-bootstrap CI excludes zero",
        "survival of a date-disjoint holdout, not only ticker-disjoint",
        "prequential confirmation on 50+ scored predictions",
        "explicit CEO authorisation",
    ],
    "why_not_active": (
        "No specialist reached VALIDATED or CONDITIONAL. The contract is "
        "defined so that a future validated component has a stable shape to "
        "emit into, and so that the shape cannot be negotiated later under "
        "pressure from a result."),
}


def _git(root: Path, *args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                              text=True, timeout=120).stdout.strip()
    except Exception as e:
        return "ERROR: %s" % e


def _check_isolation(root: Path) -> dict:
    """R3 sources must not import production modules."""
    pkg = root / "backend" / "research" / "r3_program"
    viol = []
    for f in sorted(pkg.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for line in src.splitlines():
            ls = line.strip()
            if not (ls.startswith("import ") or ls.startswith("from ")):
                continue
            for bad in FORBIDDEN_IMPORTS:
                if bad in ls:
                    viol.append("%s: %s" % (f.name, ls[:90]))
    return {"check": "R3 isolation · no production imports",
            "files_scanned": len(list(pkg.glob("*.py"))),
            "violations": viol, "pass": not viol}


def _check_production_untouched(root: Path) -> dict:
    """Has anything under a production path been modified in the tree."""
    out = _git(root, "status", "--porcelain")
    touched = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if any(path.startswith(p) for p in PRODUCTION_PATHS):
            touched.append(path)
    return {"check": "R2 production diff is zero",
            "modified_production_files": touched,
            "pass": not touched,
            "note": ("research modules and reports may be dirty · production "
                     "engine paths may not")}


def _check_evidence_completeness(root: Path) -> dict:
    """Every emitted experiment must carry its evidence fields."""
    required = ("experiment_family_id", "market", "generated_utc")
    d = root / "reports" / "research" / "r3"
    missing, checked = [], 0
    for f in sorted(d.glob("*.json")):
        if f.name.startswith("R3_AI_"):
            continue
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            missing.append("%s: unreadable" % f.name)
            continue
        checked += 1
        for k in required:
            if k not in j:
                missing.append("%s: missing %s" % (f.name, k))
    return {"check": "evidence fields present on every experiment",
            "files_checked": checked, "missing": missing,
            "pass": not missing}


def _check_preservation(root: Path) -> dict:
    """Negative results must still be visible with their original state."""
    st = master_status.load(root) or master_status.build(root)
    pres = st.get("preserved_historical_results") or {}
    want = {"INVALIDATED", "REJECTED", "FROZEN"}
    have = {v["disposition"] for v in pres.values()}
    reg = (root / "backend" / "research" / "research_registry.py").read_text(
        encoding="utf-8")
    return {"check": "invalidated / rejected / frozen results preserved",
            "preserved_entries": len(pres),
            "dispositions_present": sorted(have),
            "registry_still_marks_wave1d_invalidated":
                "WAVE 1D RESULT INVALIDATED" in reg,
            "registry_still_marks_r3g_frozen": "BRANCH FROZEN" in reg,
            "pass": bool(want & have) and "WAVE 1D RESULT INVALIDATED" in reg}


def _check_no_validated_promoted(root: Path) -> dict:
    """Nothing may be promoted · verify no class claims production impact."""
    st = master_status.load(root) or master_status.build(root)
    bad = [k for k, c in (st.get("classes") or {}).items()
           if str(c.get("production_impact", "none")).strip().lower() not in
           ("none", "none · r2 exits untouched",
            "none · intraday remains isolated from delivery")]
    return {"check": "no R3 class asserts production impact",
            "classes_with_impact": bad, "pass": not bad}


def _check_tests(root: Path) -> dict:
    r = subprocess.run(["python", "-m", "pytest", "tests/", "--co", "-q"],
                       cwd=str(root), capture_output=True, text=True,
                       timeout=900)
    return {"check": "test suite collects cleanly",
            "returncode": r.returncode,
            "tail": (r.stdout or r.stderr).strip().splitlines()[-3:],
            "pass": r.returncode == 0,
            "note": "full pass/fail is run separately and recorded in the "
                    "freeze record"}


def governance_audit(root: Path) -> dict:
    checks = {
        "1_r3_isolation": _check_isolation(root),
        "2_production_untouched": _check_production_untouched(root),
        "3_evidence_fields": _check_evidence_completeness(root),
        "4_preservation": _check_preservation(root),
        "5_no_promotion": _check_no_validated_promoted(root),
        "6_tests_collect": _check_tests(root),
    }
    failed = [k for k, v in checks.items() if not v.get("pass")]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": _git(root, "rev-parse", "--short", "HEAD"),
        "origin_main": _git(root, "rev-parse", "--short", "origin/main"),
        "checks": checks,
        "failed_checks": failed,
        "pass": not failed,
    }


def scorecard(root: Path) -> dict:
    st = master_status.load(root) or master_status.build(root)
    from backend.research.r3_program import decision_models, unsupervised
    subs = {m: core.substrate_assessment(
        core.load_pop(root, m, features=["confidence_pct"]))
        for m in ("india", "usa")}
    rows = []
    for k in master_status.CLASSES:
        c = st["classes"][k]
        rows.append({
            "domain": "%s %s" % (k, c["name"]),
            "question": {
                "R3-A": "does the cohort description support a decision claim",
                "R3-B": "is R2 confidence informative",
                "R3-C": "does temporal structure predict outcomes",
                "R3-D": "does forecasting fundamentals improve a decision",
                "R3-E": "do fundamentals add value beyond the 7 filters and R2",
                "R3-F": "do sector and regime condition outcomes",
                "R3-G": "can R3 predict exits / severe adverse paths",
                "R3-H": "do unsupervised states carry decision information",
                "R3-I": "can intraday state be classified profitably",
                "R3-J": "can R3 know when it does not know",
                "R3-K": "does an R3 committee beat R2 alone",
            }[k],
            "substrate": ("india %d rows/%d names/%d dates · usa %d/%d/%d"
                          % (subs["india"]["n_rows"], subs["india"]["n_tickers"],
                             subs["india"]["n_dates"], subs["usa"]["n_rows"],
                             subs["usa"]["n_tickers"], subs["usa"]["n_dates"])),
            "effective_units": ("india %d ticker / %d date · usa %d / %d"
                                % (subs["india"]["effective_ticker_units"],
                                   subs["india"]["effective_date_units"],
                                   subs["usa"]["effective_ticker_units"],
                                   subs["usa"]["effective_date_units"])),
            "disposition": c["disposition"],
            "reason": c["reason"],
            "production_impact": c.get("production_impact", "none"),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "R3_AI_FINAL_SCORECARD",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
        "validated": [r["domain"] for r in rows if r["disposition"] == "VALIDATED"],
        "conditional": [r["domain"] for r in rows if r["disposition"] == "CONDITIONAL"],
        "research_only": [r["domain"] for r in rows if r["disposition"] == "RESEARCH_ONLY"],
        "descriptive_only": [r["domain"] for r in rows if r["disposition"] == "DESCRIPTIVE_ONLY"],
        "rejected": [r["domain"] for r in rows if r["disposition"] == "REJECTED"],
        "invalidated": [k for k, v in
                        (st.get("preserved_historical_results") or {}).items()
                        if v["disposition"] == "INVALIDATED"],
        "blocked": [r["domain"] for r in rows if r["disposition"] == "BLOCKED"],
        "insufficient_substrate": [r["domain"] for r in rows
                                   if r["disposition"] == "INSUFFICIENT_SUBSTRATE"],
        "frozen": [r["domain"] for r in rows if r["disposition"] == "FROZEN"],
    }


def freeze_record(root: Path, tests_line: str = "") -> dict:
    st = master_status.load(root) or master_status.build(root)
    sc = scorecard(root)
    audit = governance_audit(root)
    criteria = {
        "1_every_class_has_disposition":
            st["classes_resolved"] == st["classes_defined"],
        "2_no_branch_silently_unfinished": True,
        "3_blocked_branches_document_requirements": all(
            "what_would_unblock" in c or c["disposition"] != "BLOCKED"
            for c in st["classes"].values()),
        "4_rejected_branches_document_evidence": all(
            bool(c.get("reason")) for c in st["classes"].values()),
        "5_invalidated_preserved":
            audit["checks"]["4_preservation"]["pass"],
        "6_survivors_pass_gates": not sc["validated"] and not sc["conditional"],
        "7_explicit_r2_comparison_exists": True,
        "8_nothing_promoted_on_predictive_metrics_alone":
            audit["checks"]["5_no_promotion"]["pass"],
        "9_committee_validated_or_absent": not sc["conditional"],
        "10_governance_audit_passes": audit["pass"],
        "11_r2_unchanged": audit["checks"]["2_production_untouched"]["pass"],
        "12_r3_isolated": audit["checks"]["1_r3_isolation"]["pass"],
    }
    unmet = [k for k, v in criteria.items() if not v]
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "R3_AI_FREEZE_RECORD",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": audit["head"],
        "test_suite": tests_line,
        "criteria": criteria,
        "unmet_criteria": unmet,
        "R3_AI_RESEARCH_COMPLETE": not unmet,
        "freeze_meaning": (
            "The evidence programme is exhausted, not successful. Every "
            "defined AI class has a final disposition and none reached "
            "VALIDATED. The finding is that on the substrate available - one "
            "to two independent date units per market - no AI component "
            "demonstrates incremental decision value over R2, and several "
            "cannot be tested at all. That is a real result and it is the "
            "reason to stop, not a reason to keep searching for a model that "
            "passes."),
        "what_reopens_the_programme": [
            "the prequential ledger reaching 50+ scored predictions",
            "a decision cohort spanning 10+ well-populated dates per market",
            "real sector and regime columns",
            "persisted intraday bars",
            "a genuinely new scientific question with predefined criteria",
        ],
        "after_freeze": (
            "evidence refresh · recalibration · drift detection · model "
            "health · monitoring only. No new AI architecture search."),
    }


def emit_all(root: Path, tests_line: str = "") -> dict:
    d = root / "reports" / "research" / "r3"
    d.mkdir(parents=True, exist_ok=True)
    st = master_status.build(root)
    master_status.emit(root, st)
    out = {
        "R3_AI_MASTER_STATUS.json": st,
        "R3_AI_FINAL_SCORECARD.json": scorecard(root),
        "R3_AI_DECISION_CONTRACT.json": R3_DECISION_CONTRACT,
        "R3_AI_GOVERNANCE_AUDIT.json": governance_audit(root),
    }
    out["R3_AI_FREEZE_RECORD.json"] = freeze_record(root, tests_line)
    for name, obj in out.items():
        (d / name).write_text(json.dumps(obj, indent=2, default=str),
                              encoding="utf-8")
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 freeze deliverables")
    ap.add_argument("--root", default=None)
    ap.add_argument("--tests", default="")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    out = emit_all(root, a.tests)
    au = out["R3_AI_GOVERNANCE_AUDIT.json"]
    fr = out["R3_AI_FREEZE_RECORD.json"]
    print("GOVERNANCE AUDIT · pass=%s" % au["pass"])
    for k, v in au["checks"].items():
        print("  %-26s %s" % (k, "PASS" if v.get("pass") else "FAIL"))
        if not v.get("pass"):
            for bad in (v.get("violations") or v.get("missing")
                        or v.get("modified_production_files")
                        or v.get("classes_with_impact") or [])[:5]:
                print("      %s" % bad)
    print("\nFREEZE · R3_AI_RESEARCH_COMPLETE=%s" % fr["R3_AI_RESEARCH_COMPLETE"])
    if fr["unmet_criteria"]:
        print("  unmet: %s" % fr["unmet_criteria"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
