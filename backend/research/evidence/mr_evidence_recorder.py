"""C.1 · MR Forward-Validation Trial-Accounting Hook.

CEO 2026-09-05 · wires the existing mr_forward_validation cohort output into
the Evidence Log's experiment_family_id + trial_count discipline. This is
STATISTICAL GOVERNANCE INFRASTRUCTURE · not a new research item.

Reads the existing mr_forward_validation_{market}.json produced by
backend/research/mr_forward_validation.py · does NOT re-run the MR analysis ·
records each cohort as one trial in a declared family so that downstream
Bonferroni/FDR correction is mechanical rather than reconstructed by hand.

Governance:
  · No production/R2/XLSX changes
  · No modification to mr_forward_validation.py
  · No re-computation · reads cached JSON only
  · Appends immutably to reports/research/evidence/evidence_log.jsonl
  · One evidence record per (family_id, market, cohort_key)
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from backend.research.evidence.evidence_log import append_evidence_record


FAMILY_ID_TEMPLATE = "MR_FWD_COHORT_{market}_{asof}"


def _enumerate_cohorts(mr_json: dict) -> list[dict]:
    """Flatten MR cohort_* keys into a uniform list.
    Every cohort produces one trial row: (family_id, key, sample_size, metrics).
    """
    cohorts: list[dict] = []
    # cohort_ALL (single row)
    if "cohort_ALL" in mr_json:
        cohorts.append({"key": "ALL", "kind": "overall",
                          "cohort": mr_json["cohort_ALL"]})
    # cohort_by_runner (dict)
    for k, v in (mr_json.get("cohort_by_runner") or {}).items():
        cohorts.append({"key": f"runner:{k}", "kind": "runner", "cohort": v})
    # cohort_by_investability
    for k, v in (mr_json.get("cohort_by_investability") or {}).items():
        cohorts.append({"key": f"band:{k}", "kind": "investability", "cohort": v})
    # cohort_by_runner_band
    for k, v in (mr_json.get("cohort_by_runner_band") or {}).items():
        cohorts.append({"key": f"runner_band:{k}", "kind": "runner_band",
                         "cohort": v})
    # cohort_by_entry_type
    for k, v in (mr_json.get("cohort_by_entry_type") or {}).items():
        cohorts.append({"key": f"entry_type:{k}", "kind": "entry_type",
                         "cohort": v})
    return cohorts


def record_family_to_evidence_log(root: Path, market: str,
                                     correction_method: str = "benjamini_hochberg_fdr_planned",
                                     ) -> dict:
    """Read the MR forward-validation JSON for market · record one evidence
    entry per cohort as trials within a single family. Returns summary."""
    mr_p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
    if not mr_p.exists():
        return {"status": "MR_JSON_MISSING", "market": market, "path": str(mr_p)}
    j = json.loads(mr_p.read_text(encoding="utf-8"))
    asof = str(j.get("asof", "unknown"))
    total_n_obs = int(j.get("n_observations", 0))
    horizons = j.get("forward_horizons_days", [])

    cohorts = _enumerate_cohorts(j)
    total_planned_trials = len(cohorts)
    family_id = FAMILY_ID_TEMPLATE.format(market=market, asof=asof)

    recorded_exp_ids = []
    for trial_num, ci in enumerate(cohorts, start=1):
        cohort = ci["cohort"]
        n = int(cohort.get("n", 0))
        # Pull the primary metric of this cohort · fwd_5d win rate + avg + CI
        metrics = {
            k: cohort.get(k) for k in (
                "n", "fwd_1d_avg", "fwd_1d_win_rate_pct", "fwd_1d_win_rate_ci",
                "fwd_3d_avg", "fwd_3d_win_rate_pct",
                "fwd_5d_avg", "fwd_5d_win_rate_pct",
                "fwd_10d_avg", "fwd_10d_win_rate_pct",
                "fwd_17d_avg", "fwd_17d_win_rate_pct",
            ) if k in cohort
        }
        verdict = cohort.get("statistical_verdict", "INSUFFICIENT")
        # sample tier per V2 locked thresholds
        tier = ("validation_candidate" if n >= 50
                else "stronger_evidence" if n >= 30
                else "research_signal" if n >= 15
                else "hypothesis" if n >= 5
                else "observation")

        exp_id = append_evidence_record(
            root, item_id=f"MR-{market.upper()}-{ci['kind']}",
            market=market,
            data_snapshot=asof,
            pit_status="mr_forward_validation_cached",
            fold_definition={
                "family_id": family_id,
                "trial_number": trial_num,
                "total_planned_trials": total_planned_trials,
                "cohort_key": ci["key"],
                "cohort_kind": ci["kind"],
                "horizons_days": list(horizons),
                "source_json": str(mr_p.relative_to(root)),
            },
            trial_count=total_planned_trials,   # AUDIT-03 · full family size
            parameters={"correction_method_planned": correction_method,
                         "sample_tier": tier},
            sample_size=n,
            metrics=metrics,
            statistical_test={"native_verdict": verdict},
            multiple_testing_correction={
                "method_planned": correction_method,
                "family_id": family_id,
                "trial_number": trial_num,
                "total_planned_trials": total_planned_trials,
                "applied": False,   # correction applied post-facto in family analyzer
                "note": ("This trial is one of {n} in family '{f}' · Bonferroni/FDR "
                          "correction to be applied by the family analyzer once all "
                          "trials are recorded.").format(n=total_planned_trials, f=family_id),
            },
            decision="RECORDED_TRIAL",
            artifact_paths=[str(mr_p.relative_to(root))],
        )
        recorded_exp_ids.append({"trial": trial_num, "key": ci["key"],
                                    "experiment_id": exp_id, "sample_tier": tier})

    return {
        "status": "OK",
        "market": market,
        "family_id": family_id,
        "asof": asof,
        "total_planned_trials": total_planned_trials,
        "total_obs_across_family": total_n_obs,
        "correction_method_planned": correction_method,
        "recorded_experiment_ids": recorded_exp_ids,
        "governance": ("C.1 · trial-accounting hook · every MR cohort now carries "
                        "family_id + trial_number + total_planned_trials in Evidence "
                        "Log · Bonferroni/FDR correction becomes mechanical for the "
                        "downstream family analyzer · no new experiment or production change"),
        "recorded_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
