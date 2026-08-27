"""AEGIS · Sprint M-R · Forward Validation Engine v1 · Pipeline.

Single entrypoint that runs the CEO's 14-item Forward Validation scope in
strict order and emits ONE research report at the end.

The 14 items:
   1. Ingest complete month of historical predictions
   2. Join each prediction to future market outcomes
   3. Calculate 1D/3D/5D/10D/20D returns
   4. Calculate MFE/MAE
   5. Calculate stop-hit behaviour
   6. Label WIN / LOSS / FLAT
   7. Split by R1 / R2 / Momentum
   8. Split by sector and market cap
   9. Evaluate technical / fundamental / investability features
  10. Produce winner/loser attribution
  11. Produce statistical significance / confidence where sample size permits
  12. Generate a single research report
  13. Add regression tests for the research dataset  (tests/research/*)
  14. Do NOT change production decisions

The engine is a pure orchestrator · all real work is in the per-module
implementations already shipped under backend/research/. This module
guarantees deterministic ordering and emits a JSON manifest of what ran.

Under M-R sandbox rules. Writes only under reports/research/.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_v1_pipeline.v1.0"
VERSION_TAG = "M-R.v1.0"
MANIFEST_NAME = "MR_V1_MANIFEST.json"


STAGES = [
    # (stage_number, item_id, module, description)
    (1,  "STAGE_01_ingest_and_join",    "mr_prediction_autopsy",
     "Items 1-6 · ingest history, join to parquet, compute 1/3/5/10/20D + MFE/MAE + stop-hit + WIN/LOSS labels"),
    (2,  "STAGE_02_feature_enrich",     "mr_feature_enricher",
     "Item 9 · enrich each row with RSI/MA/vol/momentum/cap frozen at prediction time"),
    (3,  "STAGE_03_market_regime",      "mr_market_regime",
     "Item 9 · index regime tag per historical day"),
    (4,  "STAGE_04_winner_loser",       "mr_winner_loser_genome",
     "Item 10 · winner vs loser attribution + ranker autopsy + band boundary"),
    (5,  "STAGE_05_studies",            "mr_studies",
     "Items 7-9 · R1/R2 scoreboard + sector + cap + technicals + fundamentals + regime + rank slot"),
    (6,  "STAGE_06_stop_loss_sweep",    "mr_stop_loss_sweep",
     "Item 5 · 12 stop policies replayed with expectancy + PF + catastrophic-rate"),
    (7,  "STAGE_07_missed_winners",     "mr_missed_winners",
     "Item 10b · false-negative discovery vs universe"),
    (8,  "STAGE_08_feature_ranking",    "mr_feature_ranking",
     "Item 9b · single ranked scoreboard of every feature by WR-spread"),
    (9,  "STAGE_09_leakage_audit",      "mr_leakage_audit",
     "Item 13b · no-lookahead + data-quality audit on the emitted dataset"),
    (10, "STAGE_10_loss_prevention",    "mr_loss_prevention",
     "Item 10c · per-loss avoidability classifier + anti-signal flags"),
    (11, "STAGE_11_control_cohort",     "mr_control_cohort",
     "Item 11 · alpha vs universe baseline · null-hypothesis check"),
    (12, "STAGE_12_score_usefulness",   "mr_score_usefulness",
     "Item 9c · KEEP / PRUNE verdict for Investability + Confidence scores"),
    (13, "STAGE_13_research_tickets",   "mr_research_ticket",
     "Governance · DRAFT tickets · 7-step promotion gate · never auto-applied"),
    (14, "STAGE_14_ai_auditor",         "mr_ai_auditor",
     "Deterministic narrative synthesis · claim/evidence/caveat for review"),
    (15, "STAGE_15_walkforward_capture","mr_walkforward_snapshot",
     "Item 12b · immutable day-0 snapshot for FUTURE walk-forward evidence"),
    (16, "STAGE_16_walkforward_daemon", "mr_walkforward_daemon",
     "M2 · Automated daemon · canonical + Momentum capture + auto-score matured"),
    (17, "STAGE_17_conditional_cohorts","mr_conditional_cohorts",
     "M2 · 2-way + 3-way conditional feature cohorts (Bonferroni-aware)"),
    (18, "STAGE_18_master_report",      "mr_master_report",
     "Item 12 · single consolidated research report · M_R_MASTER_REPORT.md"),
    (19, "STAGE_19_hypothesis_ranker",  "mr_hypothesis_ranker",
     "Rank the DRAFT tickets into a top-N shortlist for walk-forward validation"),
    (20, "STAGE_20_walkforward_experiment", "mr_walkforward_experiment",
     "Structure each shortlist hypothesis as a runnable walk-forward experiment"),
    (21, "STAGE_21_forward_validation_report", "mr_forward_validation_report",
     "AEGIS_FORWARD_VALIDATION_REPORT · CEO's 18-section master research report"),
    (22, "STAGE_22_ceo_dashboard",      "mr_ceo_dashboard",
     "CEO Dashboard · Forward Validation M1 · single-page reference"),
]


def _run_module(module: str, args: list) -> tuple:
    """Run backend.research.<module> as a subprocess with clean env."""
    cmd = [sys.executable, "-m", f"backend.research.{module}"] + args
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        ok = r.returncode == 0
        return (ok, started,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                r.returncode,
                (r.stdout or "").splitlines()[-3:],
                (r.stderr or "").splitlines()[-3:])
    except subprocess.TimeoutExpired:
        return (False, started, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                -1, [], ["TIMEOUT"])
    except Exception as e:
        return (False, started, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                -1, [], [str(e)])


def run(root: Path, market: str = "both",
        include_snapshot: bool = True,
        include_universe_scans: bool = True) -> dict:
    """Run every stage in order. Returns a manifest."""
    manifest = {
        "engine":         ENGINE_ID,
        "version_tag":    VERSION_TAG,
        "experiment_id":  EXPERIMENT_ID,
        "run_started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_date":       date.today().isoformat(),
        "market":         market,
        "stages":         [],
        "policy":         {
            "locked_layers_touched": False,
            "production_decisions_changed": False,
            "writes_under":         str(ALLOWED_WRITE_ROOT).replace("\\","/"),
        },
    }
    for num, sid, module, desc in STAGES:
        args: list = []
        if module in ("mr_prediction_autopsy","mr_feature_enricher","mr_market_regime",
                      "mr_winner_loser_genome","mr_studies","mr_stop_loss_sweep",
                      "mr_missed_winners","mr_feature_ranking","mr_leakage_audit",
                      "mr_loss_prevention","mr_control_cohort","mr_score_usefulness"):
            args = ["--market", market]
        if module == "mr_walkforward_snapshot":
            if not include_snapshot: continue
            args = ["--snapshot", "--market", market]
        if module in ("mr_missed_winners","mr_control_cohort") and not include_universe_scans:
            continue
        ok, t0, t1, rc, tail_out, tail_err = _run_module(module, args)
        manifest["stages"].append({
            "stage":       num,
            "stage_id":    sid,
            "module":      f"backend.research.{module}",
            "description": desc,
            "args":        args,
            "started_utc": t0,
            "ended_utc":   t1,
            "rc":          rc,
            "ok":          ok,
            "tail_stdout": tail_out,
            "tail_stderr": tail_err,
        })
        print(f"  [{num:2d}] {sid:32s} rc={rc} ok={ok}")
        if not ok:
            print(f"       stderr tail: {tail_err}")

    manifest["run_ended_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["n_stages_ok"]   = sum(1 for s in manifest["stages"] if s["ok"])
    manifest["n_stages_fail"] = sum(1 for s in manifest["stages"] if not s["ok"])
    manifest["all_ok"]        = manifest["n_stages_fail"] == 0

    dst = root / ALLOWED_WRITE_ROOT / MANIFEST_NAME
    dst.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="skip walk-forward snapshot capture")
    ap.add_argument("--no-universe-scans", action="store_true",
                    help="skip missed-winners + control-cohort (slow)")
    args = ap.parse_args()
    root = Path(".").resolve()
    print(f"\n======== SPRINT M-R · FORWARD VALIDATION ENGINE v1 ========")
    print(f"  version: {VERSION_TAG}  ·  market: {args.market}")
    print(f"  writes under: {ALLOWED_WRITE_ROOT}")
    print(f"  production decisions: UNCHANGED · locked layers: UNTOUCHED")
    m = run(root, args.market,
            include_snapshot=not args.no_snapshot,
            include_universe_scans=not args.no_universe_scans)
    print(f"\n  stages_ok  = {m['n_stages_ok']}")
    print(f"  stages_fail= {m['n_stages_fail']}")
    print(f"  manifest   = {ALLOWED_WRITE_ROOT}/{MANIFEST_NAME}")
    print(f"  report     = {ALLOWED_WRITE_ROOT}/M_R_MASTER_REPORT.md")
    print(f"\n  status: {'OK · foundation complete · integration DEFERRED' if m['all_ok'] else 'FAIL · see manifest'}")
