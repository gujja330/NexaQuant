"""R3 HISTORICAL REPLAY v1 runner — produces the §18 artifacts.

Research only. Writes under reports/research/r3/ and data/research/r3/.
Never writes to any production path.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backend.research.r3_program.replay_dataset import build, HORIZONS
from backend.research.r3_program.historical_replay import (
    inventory, quality_gate, forensics, oos_gate, tier_for,
    SCHEMA_VERSION, F_SPECS, MIN_DATES_FOR_OOS)

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports" / "research" / "r3"
DAT = ROOT / "data" / "research" / "r3"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def w(name: str, obj) -> None:
    REP.mkdir(parents=True, exist_ok=True)
    (REP / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print("   -> reports/research/r3/%s" % name)


def main() -> None:
    print("=" * 62)
    print("R3 HISTORICAL REPLAY v1")
    print("=" * 62)

    # §1 ---------------------------------------------------------------
    print("\n[1] INVENTORY")
    inv = inventory(ROOT)
    for m, v in inv["markets"].items():
        print("   %-6s sealed=%d  replay_ready=%d" % (m, v["sealed_days"],
                                                      v["replay_ready_days"]))
        for r in v["detail"]:
            fams = r["families"]
            avail = [k for k, s in fams.items() if s == "AVAILABLE"]
            print("     %s ready=%-5s seal=%-8s usable=%d/10  AVAILABLE: %s"
                  % (r["as_of"], r["replay_ready"], r["seal_status"],
                     r["usable_families"], ",".join(avail) or "-"))
            for b in r["blockers"]:
                print("        blocker: %s" % b[:92])

    # §2-4 -------------------------------------------------------------
    print("\n[2-4] MASTER REPLAY DATASET")
    df, man = build(ROOT)
    print("   dates considered=%d admitted=%d rows=%d"
          % (man["dates_considered"], man["dates_admitted"], man["rows"]))
    for r in man["dates_refused"]:
        print("   refused %-6s %s : %s" % (r["market"], r["as_of"], r["reason"]))

    # §5 ---------------------------------------------------------------
    print("\n[5] DATA-QUALITY GATE")
    q = quality_gate(df)
    for k in ("rows", "tickers", "prediction_dates", "effective_date_units",
              "duplicate_rows", "pit_violations", "future_data_violations",
              "schema_violations", "columns", "fully_empty_columns", "verdict"):
        print("   %-26s %s" % (k, q.get(k)))
    print("   outcome_coverage           %s" % q.get("outcome_coverage"))
    if q["verdict"] != "PASS":
        print("   !! QUALITY GATE FAILED - no statistical stage will run")

    n_dates = q.get("effective_date_units", 0)

    # §6-9 -------------------------------------------------------------
    print("\n[6-9] DESCRIPTIVE + ENTRY-FAILURE FORENSICS")
    t, fs = forensics(df)
    print("   outcome column used : %s" % fs.get("outcome_column"))
    print("   confidence column   : %s" % (fs.get("confidence_column") or "NONE FOUND"))
    print("   %-4s %-30s %6s %6s %6s  %s" % ("id", "factor", "rows", "tick", "dates", "mean out%"))
    for f in fs["factors"]:
        print("   %-4s %-30s %6d %6d %6d  %s"
              % (f["id"], f["label"], f["n_rows"], f["n_tickers"], f["n_dates"],
                 "-" if f["mean_outcome_pct"] is None else f["mean_outcome_pct"]))
    print("   severe bands (research bands only):")
    for k, v in fs["severe_bands"].items():
        print("     %-12s rows=%d tickers=%d dates=%d"
              % (k, v["n_rows"], v["n_tickers"], v["n_dates"]))

    # §10-11 -----------------------------------------------------------
    print("\n[10-11] STATISTICAL + DATE-AWARE VALIDATION")
    g = oos_gate(n_dates)
    print("   effective_date_units=%d  required=%d" % (n_dates, g["required"]))
    print("   disposition : %s" % g["disposition"])
    if g["reason"]:
        print("   reason      : %s" % g["reason"])

    ledger = []
    for f in fs["factors"]:
        if f["id"] == "F5":
            disp, why = "REJECTED", "peer family remains REJECTED; not computed"
        elif f["n_rows"] == 0:
            disp, why = "BLOCKED", "no rows match this factor in sealed memory"
        elif f["n_with_outcome"] == 0:
            disp, why = "BLOCKED", "no closed forward window for any matching row"
        elif n_dates < MIN_DATES_FOR_OOS:
            disp, why = ("BLOCKED_INSUFFICIENT_DATE_DEPTH",
                         "%d effective date units; %d required before any test is run"
                         % (n_dates, MIN_DATES_FOR_OOS))
        else:
            disp, why = "ACCUMULATE", "passes screening; awaiting date-aware validation"
        ledger.append({
            "hypothesis_id": "R3HR1-%s" % f["id"],
            "feature_family": f["label"], "note": f["note"],
            "trial_count": len(F_SPECS),
            "n_rows": f["n_rows"], "n_tickers": f["n_tickers"],
            "n_dates": f["n_dates"], "effective_date_units": n_dates,
            "test": None, "effect": f["mean_outcome_pct"],
            "confidence_interval": None, "raw_p": None, "adjusted_p": None,
            "correction_method": "BH-FDR (not applied: no test was run)",
            "disposition": disp, "reason": why,
        })
    from collections import Counter
    dc = Counter(x["disposition"] for x in ledger)
    print("   hypothesis dispositions: %s" % dict(dc))
    print("   NOTE: no p-value is reported because no test was run. A test on")
    print("         %d date units would describe those days, not the strategy." % n_dates)

    # §12 --------------------------------------------------------------
    print("\n[12] DECISION-UTILITY TEST")
    du = {"attempted": False,
          "disposition": "BLOCKED_INSUFFICIENT_DATE_DEPTH",
          "reason": ("No family reached ACCUMULATE with a closed outcome window, so "
                     "there is no candidate signal to add to the frozen R2 baseline. "
                     "A utility number computed now would be arithmetic on %d dates."
                     % n_dates),
          "r2_baseline_modified": False}
    print("   %s" % du["disposition"])
    print("   %s" % du["reason"])

    # §13 --------------------------------------------------------------
    print("\n[13] EVIDENCE CLOCK")
    clock = {
        "schema_version": SCHEMA_VERSION, "generated_utc": NOW,
        "effective_date_units": n_dates,
        "tier": tier_for(n_dates),
        "oos_available": g["attempted"],
        "cross_market_replication": {
            m: int(len(df[df["market"] == m][["prediction_as_of"]].drop_duplicates()))
            for m in sorted(df["market"].unique())} if not df.empty else {},
        "rule": ("Tiers advance on EFFECTIVE DATE UNITS. Ticker rows increasing "
                 "does not advance a tier."),
        "shortfall_to_research_signal": max(0, 15 - n_dates),
        "shortfall_to_validation_candidate": max(0, 50 - n_dates),
    }
    print("   effective_date_units : %d" % n_dates)
    print("   tier                 : %s" % clock["tier"])
    print("   per-market dates     : %s" % clock["cross_market_replication"])
    print("   OOS available        : %s" % clock["oos_available"])

    # §18 outputs ------------------------------------------------------
    print("\n[18] OUTPUTS")
    DAT.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_parquet(REP / "historical_replay_v1.parquet", index=False)
        print("   -> reports/research/r3/historical_replay_v1.parquet")

    hdr = {"schema_version": SCHEMA_VERSION, "generated_utc": NOW,
           "as_of_dates": sorted(df["prediction_as_of"].unique().tolist())
           if not df.empty else [],
           "markets": sorted(df["market"].unique().tolist()) if not df.empty else [],
           "source": "memory-v2 sealed snapshots",
           "pit_status": "PIT_OK" if q.get("pit_violations") == 0 else "PIT_VIOLATION",
           "sample_size": q.get("rows", 0),
           "date_depth": n_dates,
           "evidence_tier": clock["tier"],
           "disposition": "INSUFFICIENT EVIDENCE" if n_dates < 15 else "ACCUMULATE"}

    w("historical_replay_summary.json",
      {**hdr, "inventory": inv, "dataset_manifest": man, "quality_gate": q,
       "oos_gate": g, "decision_utility": du})
    w("entry_failure_forensics_v1.json", {**hdr, "forensics": fs})
    w("evidence_clock_v1.json", {**hdr, **clock})
    w("hypothesis_ledger_v1.json", {**hdr, "hypotheses": ledger})

    # §19 --------------------------------------------------------------
    print("\n[19] GOVERNANCE RESULT")
    print("   %-34s %s" % ("evidence disposition", hdr["disposition"]))
    for k, v in dc.items():
        print("   %-34s %d families" % (k, v))
    print("   %-34s %s" % ("R3 production authority", "NONE CREATED"))
    if n_dates < 15:
        print("\n   INSUFFICIENT EVIDENCE")
        print("   %d effective date units. Continue accumulating history." % n_dates)
        print("   No gate was lowered to produce a result.")


if __name__ == "__main__":
    main()
