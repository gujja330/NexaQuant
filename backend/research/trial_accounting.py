"""AEGIS Trial Accounting · Sprint A · pasted-plan Sec 28
CEO 2026-09-03

Every experiment family records its trial count so Deflated Sharpe /
White's Reality Check applies the correct multiple-testing correction.
Silent trial inflation is a Constitution violation.

Source of truth: configs/outcome_dataset_schema.yaml `trial_accounting` block.
This module reads it + verifies experiment output files carry the correct
trial_count_in_matrix field.

Consumers:
  - Every P0-P5 module writes trial_count_in_matrix in its output
  - This module verifies + surfaces drift
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


EXPERIMENT_FILE_MAP = {
    "P0_exit_bridge":     "r2_upgrades/p0_exit_bridge_replay_{market}.json",
    "P1_calibration":     "r2_upgrades/p1_calibration_{market}.json",
    "P2_sector_regime":   "r2_upgrades/p2_sector_regime_{market}.json",
    "P3_kg_gamma":        "r2_upgrades/p3_kg_community_{market}.json",
    "P4_cap_sector_lr":   "r2_upgrades/p4_cap_sector_{market}.json",
    "R3_gbm_baseline":    "r3/models/gbm_tier1_{market}.json",
}


def load_declared_trials(root: Path) -> dict:
    import yaml
    p = root / "configs" / "outcome_dataset_schema.yaml"
    if not p.exists(): return {}
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return cfg.get("trial_accounting", {}) or {}


def read_actual_trials(root: Path, market: str, experiment: str) -> int | None:
    rel = EXPERIMENT_FILE_MAP.get(experiment)
    if not rel: return None
    p = root / "reports" / "research" / rel.format(market=market)
    if not p.exists(): return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    # Accept a few naming variants
    for k in ("trial_count_in_matrix", "trials_run", "n_trials", "trial_count"):
        if k in d:
            try: return int(d[k])
            except (TypeError, ValueError): pass
    return None


def verify_trials(root: Path, market: str) -> dict:
    declared = load_declared_trials(root)
    issues: list[dict] = []
    seen: list[dict] = []
    for exp, decl in declared.items():
        actual = read_actual_trials(root, market, exp)
        row = {"experiment": exp, "declared": decl, "actual": actual}
        seen.append(row)
        if actual is None:
            row["status"] = "MISSING_OUTPUT"
        elif actual != decl:
            row["status"] = "DRIFT"
            issues.append(row)
        else:
            row["status"] = "OK"
    result = {
        "market": market,
        "n_experiments_declared": len(declared),
        "n_ok": sum(1 for r in seen if r.get("status") == "OK"),
        "n_missing": sum(1 for r in seen if r.get("status") == "MISSING_OUTPUT"),
        "n_drift": len(issues),
        "issues": issues,
        "trials": seen,
        "note": ("Trial count drift is a Constitution violation · silent "
                 "inflation defeats Deflated Sharpe multiple-testing "
                 "correction. Any DRIFT here must be resolved before "
                 "reporting new experiment results."),
        "verified_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    r = verify_trials(Path(args.root), args.market)
    out = Path(args.root) / "reports" / "research" / "trial_accounting"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.market}.json").write_text(
        json.dumps(r, indent=2), encoding="utf-8"
    )
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
