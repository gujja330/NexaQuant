"""Run A/B/D full cohort program · CEO 2026-09-05 · GO A/B/C/D full.

Executes 10 A-items + 8 B-items + 3 D-items × 2 markets = 42 trials.
Each recorded to Evidence Log with family_id + trial_number + total_planned_trials
via C.1's append_evidence_record hook. Applies Benjamini-Hochberg FDR at family close.

Governance:
  · No R2 production changes
  · No XLSX changes
  · Reads cached data only · never re-runs MR or NEG/POS-PNL
  · Every result classified · PROMISING / NO_LIFT / HARMFUL / INSUFFICIENT / DATA_BLOCKED
"""
from __future__ import annotations
import argparse, io, json, sys
from datetime import date, datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.evidence.abd_cohort_executor import (
    A_ITEMS, B_ITEMS, D_ITEMS, benjamini_hochberg,
)
from backend.research.evidence.evidence_log import append_evidence_record


ABD_FAMILY_TEMPLATE = "ABD_COHORT_MINE_{market}_{asof}"


def run_market(root: Path, market: str) -> dict:
    asof = date.today().isoformat()
    family_id = ABD_FAMILY_TEMPLATE.format(market=market, asof=asof)

    all_items = A_ITEMS + B_ITEMS + D_ITEMS
    total = len(all_items)
    results = []
    for trial_num, (item_id, fn) in enumerate(all_items, start=1):
        r = fn(root, market)
        results.append({"item_id": item_id, **r})

    # Extract p-values for FDR (only items that returned a metric with p_value)
    pvals = []
    for r in results:
        m = r.get("metrics") or {}
        p = m.get("p_value_two_sided")
        pvals.append(p if p is not None else None)
    q_adjusted = benjamini_hochberg(pvals)

    # Log each trial + FDR-adjusted
    for trial_num, (r, q) in enumerate(zip(results, q_adjusted), start=1):
        exp_id = append_evidence_record(
            root, item_id=f"ABD-{market.upper()}-{r['item_id']}",
            market=market,
            data_snapshot=asof,
            pit_status="cached_source_read_only",
            fold_definition={
                "family_id": family_id,
                "trial_number": trial_num,
                "total_planned_trials": total,
                "trial_key": r.get("trial_key"),
                "cohort_kind": r.get("cohort_kind"),
                "source_categories": "A+B+D",
            },
            trial_count=total,
            parameters={"executor_version": "abd_cohort_executor.v1",
                         "governance": "read-only · no production/XLSX changes"},
            sample_size=r.get("sample_size", 0),
            metrics=r.get("metrics", {}),
            statistical_test={"native_verdict": r.get("verdict"),
                                "native_note": r.get("note")},
            multiple_testing_correction={
                "method": "benjamini_hochberg_fdr",
                "family_id": family_id,
                "trial_number": trial_num,
                "total_planned_trials": total,
                "raw_p_value": pvals[trial_num - 1],
                "fdr_q_value": q,
                "applied": True,
            },
            decision=r.get("verdict"),
            artifact_paths=[])
        r["experiment_id"] = exp_id
        r["fdr_q_value"] = q

    # Family summary
    from collections import Counter
    verdicts = Counter(r["verdict"] for r in results)
    summary = {
        "family_id": family_id, "market": market, "asof": asof,
        "total_trials": total,
        "trials_by_verdict": dict(verdicts),
        "correction_method": "benjamini_hochberg_fdr",
        "results": results,
        "governance": ("C.1 trial-accounting applied · every trial logged with family_id + "
                        "trial_number + total_planned_trials + BH-FDR q-value · zero "
                        "production/XLSX changes"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = root / "reports" / "research" / "evidence" / f"abd_family_{market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = run_market(_ROOT, m)
        print(f"\n=========== {m.upper()} · {r['family_id']} ===========")
        print(f"total trials: {r['total_trials']}")
        print(f"by verdict: {r['trials_by_verdict']}")
        for res in r["results"]:
            print(f"  {res['item_id']} · {res['trial_key']:40s} · {res['verdict']:12s} · n={res.get('sample_size',0):>4} · {res.get('note','')[:80]}")


if __name__ == "__main__":
    main()
