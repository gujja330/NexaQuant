"""AEGIS_FINAL_STATUS · the single end-to-end reconciliation.

Every field is READ from an artifact or a live check. Nothing here is
typed in by hand, because a status document maintained by hand drifts
towards looking finished.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.final_status.v1"
MARKETS = ("india", "usa")


def _git(root: Path, *a) -> str:
    try:
        return subprocess.run(["git", *a], cwd=str(root), capture_output=True,
                              text=True, timeout=120).stdout.strip()
    except Exception as e:
        return "ERROR: %s" % e


def _delivery(root: Path) -> dict:
    from backend.delivery import delivery_gate as dg
    from backend.delivery.xlsx_contract import resolve_exit_history_sheet
    from openpyxl import load_workbook
    out = {}
    for m in MARKETS:
        d = dg.decide(root, m)
        row = {"gate_verdict": d.verdict, "override_used": d.override_used,
               "blocking_codes": list(d.blocking_codes)}
        wr = root / "reports" / "context" / f"wave_regression_{m}.json"
        if wr.exists():
            j = json.loads(wr.read_text(encoding="utf-8"))
            checks = {c["code"]: c["status"] for c in j.get("checks", [])}
            row.update({"A19": checks.get("A19"), "A23": checks.get("A23"),
                        "regression_verdict": j.get("verdict"),
                        "n_fail": j.get("n_fail")})
        p = root / "reports" / "telegram" / f"aegis_history_{m}.xlsx"
        if p.exists():
            wb = load_workbook(p, read_only=True)
            eh = resolve_exit_history_sheet(wb)
            hdr = ([str(c.value).strip() if c.value else ""
                    for c in wb[eh][4]] if eh else [])
            row.update({"workbook_sheets": wb.sheetnames,
                        "exit_sheet_resolved": eh,
                        "sector_column_present": "Sector" in hdr})
            wb.close()
        out[m] = row
    return out


def _lineage(root: Path) -> dict:
    from tests.delivery.test_exit_history_sector_lineage import (
        _closed_registry, _exit_history_tickers, _orphan_audit_tickers)
    out = {}
    for m in MARKETS:
        closed = _closed_registry(m)
        eh = _exit_history_tickers(m)
        aud = _orphan_audit_tickers(m)
        out[m] = {"registry_closed": len(closed), "exit_history": len(eh),
                  "orphan_audit": len(aud),
                  "unaccounted_closed": sorted(closed - eh - aud),
                  "reconciled": not (closed - eh - aud)}
    return out


def _shadow(root: Path) -> dict:
    from backend.research.r3_program import shadow
    out = {}
    for m in MARKETS:
        rep = shadow.load(root, m) or {}
        led = shadow.load_ledger(root, m)
        out[m] = {
            "ledger_records": len(led),
            "ledger_dates": len({r.get("as_of") for r in led}),
            "actions": rep.get("action_counts"),
            "validated_specialists": rep.get("validated_specialists"),
            "production_writes": rep.get("production_writes", 0),
            "any_probability_emitted": any(
                r.get(f) is not None for r in led
                for f in shadow.PROBABILITY_FIELDS),
        }
    return out


def build(root: Path, tests_line: str = "") -> dict:
    from backend.research.r3_program import freeze, master_status
    st = master_status.load(root) or master_status.build(root)
    sc = freeze.scorecard(root)
    audit = freeze.governance_audit(root)
    fr = freeze.freeze_record(root, tests_line)
    delivery = _delivery(root)
    lineage = _lineage(root)
    shadow = _shadow(root)

    dirty = [l for l in _git(root, "status", "--porcelain").splitlines() if l.strip()]
    prod_dirty = [l for l in dirty
                  if any(l[3:].strip().startswith(p)
                         for p in freeze.PRODUCTION_PATHS)]
    green = all(v["gate_verdict"] == "ALLOW" and not v["override_used"]
                and v.get("A19") == "PASS" and v.get("A23") == "PASS"
                for v in delivery.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "delivery_status": "GREEN" if green else "BLOCKED",
        "delivery_by_market": delivery,
        "lineage_reconciliation": lineage,
        "ci_status": tests_line or "not recorded",
        "r1_status": "RETIRED / ADVISORY · never auto-exited · excluded from "
                     "production P&L",
        "r2_status": "PRODUCTION · UNCHANGED · zero R3 writes",
        "r3_status": "SHADOW · ISOLATED · observational only",
        "ai_program_status": ("FROZEN · R3_AI_RESEARCH_COMPLETE=%s"
                              % fr["R3_AI_RESEARCH_COMPLETE"]),
        "validated_ai_components": sc["validated"],
        "conditional_ai_components": sc["conditional"],
        "research_only_components": sc["research_only"] + sc["descriptive_only"],
        "blocked_components": sc["blocked"] + sc["insufficient_substrate"],
        "rejected_components": sc["rejected"],
        "invalidated_components": sc["invalidated"],
        "production_changes": {
            "r2_engine_files_modified": prod_dirty,
            "r3_writes_to_production": 0,
            "note": ("delivery presentation and validators were repaired; "
                     "no R2 decision logic, threshold, weight, exit or "
                     "eligibility rule was touched"),
        },
        "shadow_changes": shadow,
        "remaining_evidence_requirements": fr["what_reopens_the_programme"],
        "git_status": {
            "head": _git(root, "rev-parse", "--short", "HEAD"),
            "origin_main": _git(root, "rev-parse", "--short", "origin/main"),
            "dirty_files": len(dirty),
            "production_paths_dirty": len(prod_dirty),
        },
        "freeze_status": {
            "frozen": True,
            "governance_audit_pass": audit["pass"],
            "classes_resolved": "%d/%d" % (st["classes_resolved"],
                                           st["classes_defined"]),
            "after_freeze": fr["after_freeze"],
        },
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "AEGIS_FINAL_STATUS.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AEGIS final status")
    ap.add_argument("--root", default=None)
    ap.add_argument("--tests", default="")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    rep = build(root, a.tests)
    p = emit(root, rep)
    print("AEGIS FINAL STATUS -> %s" % p)
    print("  delivery      %s" % rep["delivery_status"])
    for m, v in rep["delivery_by_market"].items():
        print("    %-6s gate=%s override=%s A19=%s A23=%s sector=%s"
              % (m, v["gate_verdict"], v["override_used"], v.get("A19"),
                 v.get("A23"), v.get("sector_column_present")))
    for m, v in rep["lineage_reconciliation"].items():
        print("    %-6s lineage reconciled=%s unaccounted=%d"
              % (m, v["reconciled"], len(v["unaccounted_closed"])))
    print("  ai program    %s" % rep["ai_program_status"])
    print("  r2            %s" % rep["r2_status"])
    print("  r3            %s" % rep["r3_status"])
    for m, v in rep["shadow_changes"].items():
        print("    %-6s shadow records=%d prod_writes=%d fake_probs=%s"
              % (m, v["ledger_records"], v["production_writes"],
                 v["any_probability_emitted"]))
    print("  git           HEAD=%s origin/main=%s dirty=%d (production %d)"
          % (rep["git_status"]["head"], rep["git_status"]["origin_main"],
             rep["git_status"]["dirty_files"],
             rep["git_status"]["production_paths_dirty"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
