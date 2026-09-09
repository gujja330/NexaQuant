"""R3 SHADOW INTELLIGENCE PIPELINE · operational, observational, isolated.

    R2 candidate -> R3 snapshot -> specialists -> R3_DECISION_v1
                 -> append-only shadow ledger -> forward outcome -> evidence

WHAT THIS IS
------------
The operational form of the frozen R3 architecture. It runs daily, records
what R3 would have said about each R2 candidate, and waits. It changes
nothing. R2 remains the sole production decision engine and this module
imports no part of it.

THE RULE THAT MATTERS MOST HERE
--------------------------------
Every specialist is FROZEN at a non-validated disposition. Not one of them
may emit a probability, because a probability from an unvalidated model is
indistinguishable, downstream, from a probability that means something.

So each specialist returns a STATE, not a number:

    NOT_VALIDATED           the branch resolved, but not to a usable model
    INSUFFICIENT_SUBSTRATE  the data cannot support the claim
    NOT_AVAILABLE_AT_ASOF   the input did not exist on that date
    BLOCKED                 no substrate exists at all
    DESCRIPTIVE_ONLY        real information, but not predictive

A zero is never substituted for a missing value, and an absent input never
becomes a confident 0.5. `take_probability` and its siblings stay null
until a specialist earns the right to fill them.

WHY THE ACTION IS ALWAYS ABSTAIN TODAY
---------------------------------------
ABSTAIN is not a placeholder. It is the correct output of a decision layer
whose every specialist is unvalidated: R3 genuinely does not know. When a
specialist validates, it starts contributing and the action can change -
through governance, not through code drift.

RESEARCH ONLY · SHADOW ONLY · never a production signal.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.shadow.v1"
CONTRACT_ID = "R3_DECISION_v1"

ACTIONS = ("TAKE", "AVOID", "ABSTAIN")

# Specialist -> (state, why). Read from the frozen master status at build
# time; a specialist cannot be activated by editing this table alone.
SPECIALIST_STATES = {
    "R3-A": ("DESCRIPTIVE_ONLY", "cohort description · no decision claim"),
    "R3-B": ("RESEARCH_ONLY", "confidence effect is largely ticker mix"),
    "R3-C": ("INSUFFICIENT_SUBSTRATE", "prequential below 50 scored"),
    "R3-D": ("INSUFFICIENT_SUBSTRATE", "no dates to price a forecast"),
    "R3-E": ("NOT_VALIDATED", "fundamental overlay rejected · CI spans zero"),
    "R3-F": ("NOT_AVAILABLE_AT_ASOF", "no PIT sector · regime null"),
    "R3-G": ("NOT_VALIDATED", "exit branch frozen 2026-09-08"),
    "R3-H": ("DESCRIPTIVE_ONLY", "clusters die out-of-sample"),
    "R3-I": ("BLOCKED", "no intraday bars exist"),
    "R3-J": ("RESEARCH_ONLY", "calibration built · nothing to calibrate"),
    "R3-K": ("INSUFFICIENT_SUBSTRATE", "no validated specialist to combine"),
}

VALIDATED_SPECIALISTS: tuple = ()      # empty by evidence, not by omission

PROBABILITY_FIELDS = ("take_probability", "avoid_probability",
                      "abstain_probability", "severe_loss_probability",
                      "survival_probability")


def ledger_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "r3" / "shadow"
            / f"ledger_{market.lower()}.jsonl")


def load_ledger(root: Path, market: str, raw: bool = False) -> list:
    """The ledger as EVIDENCE · one prediction per (as_of, ticker).

    The write path already skips a key it has seen, but that only holds
    while the file is the single source of truth. Git operations - a
    stash, a checkout, a rebase restoring an older copy - can hand a run
    a ledger that is missing rows it already wrote, and the next append
    then duplicates them. India carried 10 such pairs on 2026-09-09
    (GNFC recorded at 02:19 and again at 06:06).

    A duplicated prediction is not harmless: it inflates the sample and
    double-counts one opinion in any evidence tally built on top.

    So identity is enforced on READ, and the EARLIEST record wins. The
    first prediction is the honest one - a later re-prediction for the
    same date has seen more of that day, which is precisely the hindsight
    an append-only ledger exists to prevent.

    `raw=True` returns every physical row, for auditing the duplication
    itself rather than reasoning over it.
    """
    p = ledger_path(root, market)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if raw:
        return rows
    best = {}
    for r in rows:
        key = (r.get("as_of"), r.get("ticker"))
        prev = best.get(key)
        if prev is None or str(r.get("recorded_utc") or "") < str(
                prev.get("recorded_utc") or ""):
            best[key] = r
    # Preserve first-seen file order · the ledger reads chronologically.
    seen, out = set(), []
    for r in rows:
        key = (r.get("as_of"), r.get("ticker"))
        if key in seen:
            continue
        seen.add(key)
        out.append(best[key])
    return out


def _append(root: Path, market: str, recs: list) -> int:
    if not recs:
        return 0
    p = ledger_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, default=str) + "\n")
    return len(recs)


def _r2_candidates(root: Path, market: str) -> tuple:
    """R2 candidates come FROM the canonical lifecycle ARTIFACT.

    Read as a file, not through a production import. R3 could import the
    lifecycle loader and get the same rows, but then the isolation claim
    would rest on that module never growing a side effect. Reading the
    emitted artifact makes isolation structural: this package imports
    nothing from backend.delivery at all, so it cannot reach production
    even by accident.

    R3 never decides what is eligible. It only comments on what R2 has
    already selected.
    """
    p = root / "reports" / "context" / f"canonical_lifecycle_{market.lower()}.json"
    if not p.exists():
        return [], None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return [], None
    rows = [r for r in (d.get("current") or [])
            if str(r.get("engine", "")).upper() in ("R2", "MOMENTUM", "MOM")]
    return rows, d.get("asof")


def _specialist_block(root: Path, market: str, cand: dict, asof: str) -> dict:
    """Every specialist's state · states only, never invented numbers."""
    out = {}
    for key, (state, why) in sorted(SPECIALIST_STATES.items()):
        entry = {"state": state, "reason": why, "contributes": False}
        # A specialist may report FACTS it actually has, clearly separated
        # from prediction. Descriptive observations are not predictions and
        # are labelled so they cannot be mistaken for one.
        if key == "R3-F":
            sec = cand.get("sector")
            entry["observed_sector_current"] = sec
            entry["pit_sector"] = "NOT_AVAILABLE_AT_ASOF"
            entry["note"] = ("current classification only · not the sector "
                             "as of this date")
        if key == "R3-A":
            entry["observed"] = {
                "confidence_pct": cand.get("confidence_pct"),
                "pnl_pct": cand.get("pnl_pct"),
                "holding_days": cand.get("holding_days"),
                "stop_state": cand.get("stop_state")}
            entry["note"] = "descriptive facts · not a forecast"
        out[key] = entry
    return out


def build_decision(root: Path, market: str, cand: dict, asof: str) -> dict:
    """One R3_DECISION_v1 record for one R2 candidate."""
    spec = _specialist_block(root, market, cand, asof)
    contributing = [k for k, v in spec.items() if v.get("contributes")]
    rec = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "ticker": cand.get("ticker"),
        "market": market.lower(),
        "as_of": asof,
        "r2_signal": cand.get("action"),
        "r2_engine": cand.get("engine"),
        "r2_confidence_pct": cand.get("confidence_pct"),
        "r3_action": "ABSTAIN",
        # Null, not zero. A zero here would be read downstream as a
        # confident forecast of impossibility.
        **{f: None for f in PROBABILITY_FIELDS},
        "expected_horizon": None,
        "fundamental_state": spec["R3-E"]["state"],
        "technical_state": spec["R3-B"]["state"],
        "cluster_state": spec["R3-H"]["state"],
        "sector_state": spec["R3-F"]["state"],
        "regime_state": "NOT_AVAILABLE_AT_ASOF",
        "uncertainty": "TOTAL · no validated specialist contributes",
        "evidence_tier": "OBSERVATION",
        "model_versions": {"programme": "R3_FROZEN_2026-09-08",
                           "shadow": SCHEMA_VERSION},
        "experiment_family_ids": ["R3_PROGRAMME", "R3K_META_LABEL_V1"],
        "known_failure_modes": [
            "cohort is date-poor · USA is a single market episode",
            "no PIT sector or regime substrate",
            "fundamental overlay rejected · CI spans zero",
        ],
        "PIT_status": "PIT_OK · inputs as-of the candidate date",
        "OOS_status": "NOT_APPLICABLE · no model is emitting",
        "specialists": spec,
        "contributing_specialists": contributing,
        "r3_action_rationale": (
            "ABSTAIN because every specialist is at a non-validated "
            "disposition. This is R3 stating that it does not know, which "
            "is the honest output of an unvalidated decision layer - not a "
            "placeholder and not a neutral default."),
        "production_impact": "NONE · shadow only · never a production signal",
        "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Filled later by score_outcomes · never at prediction time.
        "outcome": None,
    }
    return rec


def run(root: Path, market: str) -> dict:
    cands, asof = _r2_candidates(root, market)
    if asof is None:
        return {"market": market, "error": "no lifecycle dataset"}
    existing = {(r.get("as_of"), r.get("ticker")) for r in load_ledger(root, market)}
    new = []
    for c in cands:
        key = (asof, c.get("ticker"))
        if key in existing:
            continue                    # append-only · never rewritten
        new.append(build_decision(root, market, c, asof))
    n = _append(root, market, new)
    led = load_ledger(root, market)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "market": market.lower(),
        "as_of": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "r2_candidates_seen": len(cands),
        "decisions_written_this_run": n,
        "ledger_total": len(led),
        "ledger_dates": len({r.get("as_of") for r in led}),
        "ledger_tickers": len({r.get("ticker") for r in led}),
        "action_counts": {a: sum(1 for r in led if r.get("r3_action") == a)
                          for a in ACTIONS},
        "validated_specialists": list(VALIDATED_SPECIALISTS),
        "specialist_states": {k: v[0] for k, v in sorted(SPECIALIST_STATES.items())},
        "status": ("R3 SHADOW · OBSERVATIONAL ONLY · DO NOT USE AS A "
                   "PRODUCTION SIGNAL"),
        "production_writes": 0,
    }


def score_outcomes(root: Path, market: str) -> dict:
    """Attach realised outcomes to past predictions · never edits a prediction.

    Outcomes are written to a SEPARATE outcomes file keyed by
    (as_of, ticker). The prediction ledger stays append-only and
    byte-stable, so a prediction can never be quietly improved after its
    result is known.
    """
    from backend.research.r3_program import core
    led = load_ledger(root, market)
    if not led:
        return {"market": market, "scored": 0}
    fwd = {}
    for horizon in ("fwd_5d_pct", "fwd_10d_pct", "fwd_20d_pct"):
        for r in core.load_pop(root, market, fwd_key=horizon):
            fwd.setdefault((r["date"], r["ticker"]), {})[horizon] = r["fwd"]
    out_p = (root / "reports" / "research" / "r3" / "shadow"
             / f"outcomes_{market.lower()}.jsonl")
    have = set()
    if out_p.exists():
        for line in out_p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    o = json.loads(line)
                    have.add((o.get("as_of"), o.get("ticker")))
                except Exception:
                    pass
    rows = []
    for r in led:
        k = (r.get("as_of"), str(r.get("ticker") or "").upper())
        if k in have or k not in fwd:
            continue
        rows.append({"as_of": k[0], "ticker": k[1], "market": market.lower(),
                     **fwd[k],
                     "scored_utc": datetime.now(timezone.utc)
                     .isoformat(timespec="seconds")})
    if rows:
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with out_p.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    return {"market": market.lower(), "scored": len(rows),
            "total_outcomes": len(have) + len(rows),
            "note": "outcomes are a separate append-only file · predictions "
                    "are never edited after the fact"}


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "r3" / "shadow"
         / f"summary_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "r3" / "shadow"
         / f"summary_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 shadow pipeline")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--score", action="store_true",
                    help="attach matured outcomes to past predictions")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run(root, m)
        if rep.get("error"):
            print(f"R3-SHADOW:{m} · {rep['error']}")
            continue
        emit(root, rep)
        print(f"R3-SHADOW:{m} · asof {rep['as_of']} · R2 candidates "
              f"{rep['r2_candidates_seen']} · written "
              f"{rep['decisions_written_this_run']} · ledger "
              f"{rep['ledger_total']} over {rep['ledger_dates']} date(s)")
        print(f"    actions {rep['action_counts']} · validated specialists "
              f"{rep['validated_specialists'] or 'none'} · production writes "
              f"{rep['production_writes']}")
        if a.score:
            s = score_outcomes(root, m)
            print(f"    outcomes scored this run {s['scored']} · total "
                  f"{s['total_outcomes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
