"""R3 research runner for CI · classifies every attempt into one state.

WHY A SCRIPT AND NOT SHELL IN THE YAML
--------------------------------------
The states below are the whole point of this job, and shell conditionals
in a workflow cannot be unit-tested. Two defects this repository has
already paid for came from exactly that: a `|| echo` that masked the
orchestrator's exit code, and a guard that reported success on runs where
nothing executed.

THE FIVE TERMINAL STATES
------------------------
RECORDED             at least one decision was persisted
ZERO_COVERAGE_OK     ran cleanly, no NEW sealed snapshot to process
SKIPPED_BY_GUARD     deliberately not run (upstream failed, or already
                     processed) · exit 0 but NEVER reported as a
                     successful research observation
EXECUTION_FAILURE    the decision or resolution step raised
PERSISTENCE_FAILURE  decisions were computed but the ledger did not grow

PERSISTENCE_FAILURE is the one that matters most. A run that decides and
fails to write must exit NON-ZERO, otherwise the research ledger silently
loses observations while the workflow reads green - the same shape as the
five consecutive guard-skipped runs that left artifact persistence
unverified for days.

Every attempt appends to coverage_<market>.jsonl, including failures, so
"it was attempted and failed" is distinguishable from "it never ran".
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

STATES = ("RECORDED", "ZERO_COVERAGE_OK", "SKIPPED_BY_GUARD",
          "EXECUTION_FAILURE", "PERSISTENCE_FAILURE")

# Only these two exit non-zero · a skip is not a failure, and an honest
# zero-coverage run is not one either.
FAILING_STATES = ("EXECUTION_FAILURE", "PERSISTENCE_FAILURE")


def _emit(root: Path, market: str, payload: dict) -> Path:
    from backend.research.r3_program.shadow_recommender import coverage_path
    p = coverage_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")
    return p


def _state(market: str, state: str, **kw) -> dict:
    assert state in STATES, "unknown state %r" % state
    return {"runner": "aegis.r3.research_ci.v1", "market": market,
            "terminal_state": state,
            "is_research_observation": state == "RECORDED",
            "run_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"), **kw}


def run_market(root: Path, market: str,
               upstream_conclusion: str = "success") -> dict:
    """Process one market. Returns the terminal-state payload."""
    from backend.research.r3_program import shadow_recommender as sr

    # ── upstream gate · an upstream failure is NOT a research skip we
    # can treat as fine, but it is also not OUR failure. Record it.
    if str(upstream_conclusion).lower() != "success":
        return _state(market, "SKIPPED_BY_GUARD",
                      reason="UPSTREAM_%s" % str(upstream_conclusion).upper(),
                      detail=("the snapshot-producing workflow did not "
                              "succeed, so no sealed snapshot can be "
                              "trusted · this is NOT a research observation"))

    ledger = sr.ledger_path(root, market)
    rows_before = len(sr._read_jsonl(ledger))

    # ── duplicate protection · identity is (as_of, ENGINE VERSION)
    #
    # CEO 2026-10-28 · DEFECT FIXED. This keyed on as_of alone. Because
    # decision_id includes the engine version, a policy bump produces
    # genuinely new decisions - but this check reported
    # ALL_SEALED_DATES_ALREADY_PROCESSED and returned before sr.run() was
    # ever called, so a v2 policy would have recorded NOTHING, for ever,
    # while the workflow reported green. Driven and confirmed:
    #     first run          -> RECORDED
    #     same policy again  -> ZERO_COVERAGE_OK   (correct)
    #     after policy bump  -> ZERO_COVERAGE_OK   (wrong, and permanent)
    #
    # Including the engine version re-opens every sealed date for a new
    # policy while still de-duplicating within one, which is what the
    # ledger's own identity already meant.
    try:
        sealed = set(sr.snapshot_dates(root, market))
        engine = sr.ENGINE_VERSION
        done = {(r.get("as_of"), r.get("engine_version"))
                for r in sr._read_jsonl(ledger)}
        unprocessed = sorted(d for d in sealed if (d, engine) not in done)
    except Exception as e:
        return _state(market, "EXECUTION_FAILURE",
                      reason="SNAPSHOT_DISCOVERY_FAILED",
                      error="%s: %s" % (type(e).__name__, e))

    if not sealed:
        return _state(market, "ZERO_COVERAGE_OK",
                      reason="NO_SEALED_SNAPSHOT",
                      sealed_dates=0, rows_before=rows_before)
    if not unprocessed:
        return _state(market, "ZERO_COVERAGE_OK",
                      reason="ALL_SEALED_DATES_ALREADY_PROCESSED",
                      sealed_dates=len(sealed), rows_before=rows_before,
                      engine_version=engine)

    # ── decide + persist
    try:
        rep = sr.run(root, market)
    except Exception as e:
        return _state(market, "EXECUTION_FAILURE", reason="DECIDE_RAISED",
                      error="%s: %s" % (type(e).__name__, e),
                      traceback=traceback.format_exc()[-2000:])

    rows_after = len(sr._read_jsonl(ledger))
    decided = int(rep.get("recorded_this_run") or 0)

    # ── THE check · computed but not written is a failure, not a success
    if decided > 0 and rows_after <= rows_before:
        return _state(market, "PERSISTENCE_FAILURE",
                      reason="DECIDED_BUT_LEDGER_DID_NOT_GROW",
                      decided=decided, rows_before=rows_before,
                      rows_after=rows_after,
                      detail=("%d decisions were computed and the ledger did "
                              "not grow · the observations are lost"
                              % decided))
    if decided == 0:
        return _state(market, "ZERO_COVERAGE_OK",
                      reason="NOTHING_NEW_AFTER_DECIDE",
                      sealed_dates=len(sealed), rows_before=rows_before,
                      rows_after=rows_after)

    # ── resolve matured horizons · a resolution failure does not undo a
    # successful persistence, so it is reported without downgrading the
    # RECORDED state the decisions earned.
    outcome_rep, outcome_err = None, None
    try:
        from backend.research.r3_program import experiment_outcomes as eo
        outcome_rep = eo.resolve(root, market)
    except Exception as e:
        outcome_err = "%s: %s" % (type(e).__name__, e)

    clock = sr.read_clock_start(root, market)
    return _state(
        market, "RECORDED",
        decided=decided, rows_before=rows_before, rows_after=rows_after,
        dates_recorded=rep.get("dates_recorded"),
        prospective_rows=rep.get("prospective_rows"),
        prospective_dates=rep.get("prospective_dates"),
        evidence_class=rep.get("evidence_class"),
        clock_started=bool(clock),
        clock_start_utc=(clock or {}).get("observed_start_utc"),
        outcomes_appended=(outcome_rep or {}).get("resolved_this_run"),
        outcomes_total=(outcome_rep or {}).get("outcomes_total"),
        outcomes_pending=(outcome_rep or {}).get("pending_keys"),
        outcome_error=outcome_err,
        validation_status="EXPERIMENTAL · UNVALIDATED · research only")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", required=True,
                    choices=["india", "usa", "both"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--upstream-conclusion", default="success",
                    help="conclusion of the snapshot-producing workflow")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    markets = ["india", "usa"] if a.market == "both" else [a.market]

    worst = 0
    for m in markets:
        payload = run_market(root, m, a.upstream_conclusion)
        _emit(root, m, payload)
        print("R3-RESEARCH-CI:%s · %s · %s"
              % (m, payload["terminal_state"], payload.get("reason", "")))
        for k in ("decided", "prospective_rows", "outcomes_appended",
                  "outcomes_pending", "clock_start_utc", "error"):
            if payload.get(k) is not None:
                print("    %-18s %s" % (k, payload[k]))
        if payload["terminal_state"] in FAILING_STATES:
            worst = 1
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
