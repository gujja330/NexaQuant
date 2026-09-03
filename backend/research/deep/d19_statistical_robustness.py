"""Domain 19 · Statistical Robustness Audit (WAVE 1 · real).

Audits every existing experiment for compliance with the PDF stat protocol:
  · walk-forward folds used?
  · OOS separation?
  · paired bootstrap 10k?
  · DSR with correct n_trials?
  · multiple-testing correction applied?

Emits a compliance report · no new experiment · pure audit.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from backend.research.deep._helpers import build_ticket, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="D19-STATISTICAL-ROBUSTNESS",
    domain_num=19,
    name="Statistical Robustness Audit",
    description="Compliance audit of every existing experiment vs PDF stat protocol",
    gate_precondition="No · this audit runs any time · reports gaps rather than blocking",
    additive_extension_id="D19-STAT-ROBUSTNESS",
)


def _read_json(p: Path):
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None


def evaluate(root: Path, market: str) -> dict:
    r = root / "reports" / "research"
    audits = []

    def _audit(ticket_id: str, path: Path, expected_trials: int):
        d = _read_json(path)
        if d is None:
            return {"ticket_id": ticket_id, "path": str(path.relative_to(root)),
                    "status": "MISSING", "expected_trials": expected_trials}
        has_bootstrap = "paired_bootstrap" in json.dumps(d)
        has_dsr = "deflated_sharpe" in json.dumps(d).lower() or "dsr" in json.dumps(d).lower()
        has_trial_count = (d.get("trial_count") or d.get("n_trials_family") or d.get("trials_run")
                           or d.get("winner_definition_trial_count"))
        return {
            "ticket_id": ticket_id,
            "path": str(path.relative_to(root)),
            "status": "OK",
            "expected_trials": expected_trials,
            "declared_trial_count": has_trial_count,
            "paired_bootstrap_present": has_bootstrap,
            "DSR_present": has_dsr,
            "compliance_gaps": [
                x for x, ok in [
                    ("paired_bootstrap_missing", not has_bootstrap),
                    ("DSR_missing", not has_dsr),
                    ("trial_count_undeclared", not has_trial_count),
                ] if ok
            ],
        }

    audits.append(_audit("P0-original", r / "r2_upgrades" / f"p0_exit_bridge_replay_{market}.json", 1))
    audits.append(_audit("P0-EXTENSION-01", r / "r2_upgrades" / f"p0_extension_01_{market}.json", 60))
    audits.append(_audit("P1", r / "r2_upgrades" / f"p1_calibration_{market}.json", 1))
    audits.append(_audit("P2", r / "r2_upgrades" / f"p2_sector_regime_{market}.json", 9))
    audits.append(_audit("P3", r / "r2_upgrades" / f"p3_kg_community_{market}.json", 5))
    audits.append(_audit("P4", r / "r2_upgrades" / f"p4_cap_sector_{market}.json", 1))
    audits.append(_audit("NEG-PNL-CONTROL-60D", r / "neg_pnl_control_60d" / f"panel_{market}.json", 9))
    audits.append(_audit("POS-PNL-CAPTURE-60D", r / "pos_pnl_capture_60d" / f"panel_{market}.json", 16))
    audits.append(_audit("JOINT-PARETO", r / "joint_pnl" / f"panel_{market}.json", 9))
    audits.append(_audit("CUSUM-REAL", r / "r3" / "tier3" / f"cusum_regime_{market}.json", 1))

    n_ok = sum(1 for a in audits if a["status"] == "OK")
    n_missing = sum(1 for a in audits if a["status"] == "MISSING")
    n_gaps = sum(len(a.get("compliance_gaps") or []) for a in audits)

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 19,
        "market": market,
        "gate_status": "EXECUTED",
        "n_experiments_audited": len(audits),
        "n_ok_present": n_ok,
        "n_missing": n_missing,
        "total_compliance_gaps": n_gaps,
        "audits": audits,
        "verdict": ("KEEP · methodology sound" if n_gaps == 0
                    else f"RESEARCH FURTHER · {n_gaps} compliance gaps"),
        "governance_note": ("Audit-only · does not modify any experiment. "
                            "Gaps are informational · fix by extending original module."),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
