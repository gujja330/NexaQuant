"""R3 Pre-Entry Failure Intelligence — run the experiment, then walk the ladder.

Research only. Writes under reports/research/r3/failure_intelligence_v1/.
The ladder can conclude at most READY_FOR_AUTHORIZATION; it never integrates.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from backend.research.r3_program.discovery_lab import build_panel, panel_hash, SEED
from backend.research.r3_program.market_memory import add_market_family, MARKET_COLS
from backend.research.r3_program.failure_intelligence import (
    SCHEMA_VERSION, SEVERE_PCT, DEEP_MAE_PCT, label_failures,
    train_failure_model, permutation_test, leave_ticker_out,
    decision_value, cost_sensitivity, flag_rate_sweep, risk_decile_profile)
from backend.research.r3_program import promotion_ladder as PL

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "research" / "r3" / "failure_intelligence_v1"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
STRIDE = 5

STOCK = ["ret_1d", "ret_5d", "ret_10d", "ret_20d", "ret_60d", "vol_20", "vol_60",
         "vol_ratio", "dd_60", "pos_60", "skew_20", "kurt_20", "slope_20",
         "vol_ratio_5v20"]


def w(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print("   -> %s" % (OUT / name).relative_to(ROOT))


def strip(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


def main():
    t0all = time.time()
    print("=" * 70)
    print("R3 PRE-ENTRY FAILURE INTELLIGENCE v1")
    print("=" * 70)
    per_market, ladders = {}, []

    for m in ("india", "usa"):
        print("\n### %s" % m.upper())
        t0 = time.time()
        p, _s, meta = build_panel(ROOT, m, stride=STRIDE)
        p = add_market_family(p)
        p = label_failures(p)
        feats = [c for c in STOCK + MARKET_COLS if c in p.columns]
        p = p.dropna(subset=feats).reset_index(drop=True)
        sev = p["y_severe"].dropna()
        print("  panel rows=%d tickers=%d dates=%d feats=%d  %.1fs"
              % (len(p), p["ticker"].nunique(), p["date"].nunique(), len(feats),
                 time.time() - t0))
        print("  base rate: severe(<=%.0f%%)=%.2f%%   deep MAE(<=%.0f%%)=%.2f%%"
              % (SEVERE_PCT, 100 * sev.mean(), DEEP_MAE_PCT,
                 100 * p["y_deep_mae"].dropna().mean()))

        res = {}
        for label in ("y_severe", "y_deep_mae"):
            t0 = time.time()
            r = train_failure_model(p, feats, label=label)
            if r.get("status") != "OK":
                print("  %s: %s" % (label, r.get("status")))
                res[label] = r
                continue
            print("  %s  %.1fs  AUC train=%.4f test=%.4f  AP=%.4f  base_test=%.2f%%"
                  % (label, time.time() - t0, r["auc_train"], r["auc_test"],
                     r["ap_test"], r["base_rate_test_pct"]))
            for op in r["operating_points_test"]:
                print("       flag %-5s%%  precision %-6s%%  base %-6s%%  LIFT %-6s  recall %s%%"
                      % (op["flag_rate_pct"], op["precision_pct"],
                         op["base_rate_pct"], op["lift"], op["recall_pct"]))
            res[label] = r

        # BOTH labels walk the ladder. They were pre-registered together in
        # failure_intelligence.label_failures before any result was seen, so
        # evaluating both is accounting rather than selection - but it is two
        # trials and is declared as two.
        ok_labels = [k for k, v in res.items() if v.get("status") == "OK"]
        if not ok_labels:
            per_market[m] = {"status": "NO_MODEL"}
            continue
        per_market[m] = {"models": {k: strip(v) for k, v in res.items()},
                         "panel": {**meta, "features": feats},
                         "trial_count": len(ok_labels),
                         "labels_evaluated": ok_labels,
                         "per_label": {}}

        for label in ok_labels:
            primary = res[label]
            print("\n  --- ladder for %s (trial %d of %d) ---"
                  % (label, ok_labels.index(label) + 1, len(ok_labels)))
            t0 = time.time()
            perm = permutation_test(primary, feats)
            print("  permutation (within-date) %.1fs: observed=%.4f null=%.4f+-%.4f z=%s above_null=%s"
                  % (time.time() - t0, perm["observed_auc_test"], perm["null_auc_mean"],
                     perm["null_auc_sd"], perm["z_vs_null"], perm["above_null"]))
            lto = leave_ticker_out(primary, feats)
            print("  leave-ticker-out: folds=%s auc %.4f..%.4f all_above_half=%s"
                  % (lto.get("n_folds"), lto.get("auc_min", float("nan")),
                     lto.get("auc_max", float("nan")), lto.get("all_above_half")))
            dv = decision_value(primary)
            print("  decision value @20%% flag: severe %.2f%% -> %.2f%%  avoided=%d "
                  "sacrificed=%d ratio=%s  expectancy delta=%s"
                  % (dv["severe_rate_baseline_pct"], dv["severe_rate_after_avoiding_pct"],
                     dv["severe_losses_avoided"], dv["winners_sacrificed"],
                     dv["avoided_to_sacrificed_ratio"], dv["expectancy_delta_pct"]))
            sweep = flag_rate_sweep(primary)
            prof = risk_decile_profile(primary)
            print("  flag-rate sweep: %s" % sweep.get("verdict"))
            for q in sweep.get("points", []):
                print("     flag %-5s%% avoided=%-5d sacrificed=%-5d ratio=%-6s E[delta]=%s"
                      % (q["flag_rate_pct"], q["severe_losses_avoided"],
                         q["winners_sacrificed"], q["avoided_to_sacrificed_ratio"],
                         q["expectancy_delta_pct"]))
            if prof.get("status") == "OK":
                f, rr = prof["flagged"], prof["rest"]
                print("  MECHANISM: flagged vol=%.1f mean=%+.2f%% biggain=%.1f%% severe=%.1f%%"
                      % (f["mean_vol_20"], f["mean_fwd20_pct"],
                         f["big_gain_ge_p10_pct"], f["severe_le_m5_pct"]))
                print("             rest    vol=%.1f mean=%+.2f%% biggain=%.1f%% severe=%.1f%%"
                      % (rr["mean_vol_20"], rr["mean_fwd20_pct"],
                         rr["big_gain_ge_p10_pct"], rr["severe_le_m5_pct"]))
            cs = cost_sensitivity(dv)
            print("  cost sensitivity: %s"
                  % {q["cost_bps"]: q["expectancy_delta_after_cost_pct"] for q in cs["points"]})

            per_market[m]["per_label"][label] = {
                "permutation": perm, "leave_ticker_out": lto,
                "decision_value": dv, "cost_sensitivity": cs,
                "flag_rate_sweep": sweep, "risk_decile_profile": prof}

            # ---- walk the ladder -----------------------------------------
            ops = primary["operating_points_test"]
            best_lift = max((o["lift"] or 0) for o in ops) if ops else 0
            checks = {
                "DISCOVERY": {
                    "passed": bool(perm.get("above_null")),
                    "auc_test": primary["auc_test"],
                    "null_auc_max": perm.get("null_auc_max"),
                    "z_vs_null": perm.get("z_vs_null"),
                    "reason": ("AUC exceeds every within-date permutation"
                               if perm.get("above_null") else
                               "AUC is inside the within-date permutation null")},
                "REPEATABILITY": {
                    "passed": bool(lto.get("all_above_half")),
                    "leave_ticker_out_auc_min": lto.get("auc_min"),
                    "n_folds": lto.get("n_folds"),
                    "reason": ("holds on every held-out ticker fold"
                               if lto.get("all_above_half") else
                               "collapses on at least one held-out ticker fold")},
                "TEMPORAL": {
                    "passed": bool(primary["auc_test"] > 0.55),
                    "auc_train": primary["auc_train"], "auc_test": primary["auc_test"],
                    "split": primary["split"],
                    "reason": "chronological split with %d-day embargo"
                              % primary["split"]["embargo_days"]},
                "ROBUSTNESS": {
                    "passed": bool(lto.get("all_above_half") and best_lift > 1.15),
                    "best_lift": best_lift,
                    "reason": "best lift over base rate across operating points"},
                "INCREMENTAL": {
                    "passed": False,
                    "reason": ("NOT MEASURABLE: incremental value over R2 needs R2 "
                               "scores on the same rows, and sealed R2 memory covers "
                               "3 dates against this panel's %d."
                               % p["date"].nunique())},
                "DECISION": {
                    "passed": bool(dv["expectancy_delta_pct"] > 0
                                   and dv["severe_rate_after_avoiding_pct"]
                                   < dv["severe_rate_baseline_pct"]),
                    "expectancy_delta_pct": dv["expectancy_delta_pct"],
                    "avoided_to_sacrificed_ratio": dv["avoided_to_sacrificed_ratio"]},
                "ECONOMICS": {
                    "passed": bool(cs.get("survives_all_costs")),
                    "points": cs.get("points")},
                "SHADOW": {
                    "passed": False,
                    "reason": "no shadow deployment has been run for this discovery"},
            }
            lad = PL.evaluate("R3-FAILURE-INTEL-%s-%s" % (m.upper(), label.upper()), m, checks)
            ladders.append(lad.to_dict())
            print("  LADDER: %s  (highest passed: %s)"
                  % (lad.verdict, lad.highest_gate_passed))
            for g in lad.gates:
                mark = {"PASS": "PASS", "FAIL": "FAIL", "NOT_REACHED": "  - ",
                        "BLOCKED_INSUFFICIENT_EVIDENCE": "BLKD",
                        "REQUIRES_HUMAN_ACT": "HUMAN"}.get(g.status, g.status)
                print("     %-6s %-14s %s" % (mark, g.gate, (g.reason or "")[:64]))

    # engineering queue, kept separate on purpose
    eng = [
        PL.engineering_fix("CANON-2", "tail() applied before cutoff shrinks "
                           "historical windows to 0 bars at 6 months", False,
                           "reports/research/r3/R3_SUBSTRATE_DEFECTS.json"),
        PL.engineering_fix("CANON-1", "lookback_days=90 makes sma_200 "
                           "permanently unpopulated", True,
                           "reports/research/r3/R3_SUBSTRATE_DEFECTS.json"),
        PL.engineering_fix("CANON-3", "no usable sector labels in either market",
                           True, "reports/research/r3/R3_SUBSTRATE_DEFECTS.json"),
    ]

    hdr = {"schema_version": SCHEMA_VERSION, "generated_utc": NOW, "seed": SEED,
           "severe_pct": SEVERE_PCT, "deep_mae_pct": DEEP_MAE_PCT,
           "governance": {"r2_modified": False, "r1_modified": False,
                          "r3_production_writes": 0, "stops_changed": False,
                          "exits_changed": False, "workbook_changed": False,
                          "max_verdict": "READY_FOR_AUTHORIZATION"}}
    print("\n### OUTPUTS")
    w("failure_intelligence.json", {**hdr, "markets": per_market})
    w("promotion_ladder.json",
      {**hdr, "ladder_definition": [{"gate": g, "question": q} for g, q in PL.GATES],
       "human_gates": list(PL.HUMAN_GATES), "results": ladders,
       "summary": PL.summarise(ladders)})
    w("engineering_queue.json",
      {**hdr, "queue": "ENGINEERING_AUTHORIZATION", "items": eng,
       "note": ("Separate from the research ladder by design. A defect fix is "
                "not a positive research outcome and must never be counted as "
                "one.")})
    s = PL.summarise(ladders)
    w("summary.json", {**hdr, "ladder_summary": s,
                       "per_ladder": [{"discovery_id": l["discovery_id"],
                                       "halted_at": l["halted_at"],
                                       "verdict": l["verdict"],
                                       "highest_gate_passed": l["highest_gate_passed"]}
                                      for l in ladders],
                       "trial_accounting": {
                           "labels_pre_registered": ["y_severe", "y_deep_mae"],
                           "trials_run": len(ladders),
                           "note": ("Both labels were defined before any result "
                                    "was seen. Reporting only the stronger one "
                                    "would have been selection.")}})
    print("\n### LADDER SUMMARY")
    for k, v in s["verdicts"].items():
        print("   %-34s %d" % (k, v))
    print("   halted at: %s" % s["halted_at"])
    print("   ready for authorization: %s" % (s["ready_for_authorization"] or "NONE"))
    print("   in pipeline: %s" % (s["in_pipeline"] or "NONE"))
    print("\ntotal %.1fs" % (time.time() - t0all))


if __name__ == "__main__":
    main()
