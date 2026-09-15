"""Daily evidence ledger and machine-readable research triggers.

WHERE THE THRESHOLDS COME FROM
------------------------------
They are not invented here. `backend/benchmark/report.py` already declares the
governance minimums:

    SIGNIFICANCE_MIN_SAMPLES   = 30
    INSTITUTIONAL_MIN_SAMPLES  = 100

Those constants are reused unchanged. What IS corrected is the unit they are
counted in. The benchmark module counts closed positions; the 2026-09-15
evidence gate established that rows are not independent evidence — the admitted
set overlaps ~71% day to day and daily mean returns carry lag-1 autocorrelation
~0.64. So the same numbers are applied to INDEPENDENT DATE UNITS.

    30 independent units  -> READY_FOR_VALIDATION
    100 independent units -> INSTITUTIONAL

A horizon of h days consumes h dates per independent unit, so a 5-day family
needs 30 x 5 = 150 PIT-valid dates before its first gate opens.

DUPLICATE RUNS
--------------
A day is one information date however many times it is re-run. The ledger keys
on (market, asof); repeated runs update `n_runs` and never add evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.memory.daily_snapshot import ROOT_DIRNAME, PIT_OK, PIT_PARTIAL

try:  # reuse the declared governance constants
    from backend.benchmark.report import (
        SIGNIFICANCE_MIN_SAMPLES, INSTITUTIONAL_MIN_SAMPLES)
except Exception:  # pragma: no cover - benchmark module optional at import time
    SIGNIFICANCE_MIN_SAMPLES, INSTITUTIONAL_MIN_SAMPLES = 30, 100

GATE_READY = SIGNIFICANCE_MIN_SAMPLES        # independent date units
GATE_INSTITUTIONAL = INSTITUTIONAL_MIN_SAMPLES

# Families and the horizon each would be tested at. Horizons are the ones
# already pre-registered in the severe-loss target ladder; nothing new.
FAMILY_HORIZON = {
    "sector": 5, "market_cap": 5, "fundamentals": 10,
    "earnings": 10, "macro": 5, "intermarket": 5,
}


def _days(root: Path, market: str) -> list[Path]:
    d = Path(root) / ROOT_DIRNAME / market.lower()
    if not d.exists():
        return []
    return sorted((p for p in d.iterdir() if p.is_dir() and (p / "SEALED").exists()),
                  key=lambda p: p.name)


def ledger(root: Path, market: str) -> list[dict]:
    """§9. One row per information DATE, never per run."""
    rows: list[dict] = []
    for day in _days(root, market):
        s = json.loads((day / "snapshot.json").read_text(encoding="utf-8"))
        prov = s.get("provenance", {})
        fam = s.get("families", {})
        n_rev = 0
        rd = day / "revisions"
        if rd.exists():
            n_rev = sum(1 for p in rd.iterdir() if p.is_dir())

        def cov(name: str) -> str:
            p = prov.get(name, {})
            return p.get("pit_status", "ABSENT")

        dec = fam.get("r2_decision") or {}
        decisions = dec.get("current") or []
        rows.append({
            "run_id": (s.get("content_hash") or "")[:12],
            "market": market.lower(),
            "asof": s.get("asof"),
            "n_runs": 1 + n_rev,          # re-runs never add evidence
            "counts_as_evidence": 1,
            "universe_count": len(fam.get("universe") or []),
            "sector_coverage": cov("sector"),
            "cap_coverage": cov("market_cap"),
            "fundamental_coverage": cov("fundamentals"),
            "earnings_coverage": cov("earnings"),
            "macro_coverage": cov("macro"),
            "intermarket_coverage": cov("intermarket"),
            "feature_schema": s.get("fingerprints", {}).get("feature_schema_fingerprint"),
            "r2_version": prov.get("r2_config", {}).get("observation_date"),
            "r2_config_hash": s.get("fingerprints", {}).get("r2_config_fingerprint"),
            "decision_count": len(decisions),
            "outcome_pending_count": len(decisions),   # forward outcomes not yet due
            "sealed_utc": s.get("sealed_utc"),
        })
    return rows


def pit_valid_dates(root: Path, market: str) -> dict[str, int]:
    """§5. PIT-valid date counts PER FAMILY. PARTIAL does not count."""
    out: dict[str, int] = {}
    for day in _days(root, market):
        s = json.loads((day / "snapshot.json").read_text(encoding="utf-8"))
        for fam, p in s.get("provenance", {}).items():
            if p.get("pit_status") == PIT_OK:
                out[fam] = out.get(fam, 0) + 1
    return dict(sorted(out.items()))


def triggers(root: Path, market: str) -> list[dict]:
    """§10. Machine-readable readiness. No model is run to populate these."""
    pv = pit_valid_dates(root, market)
    out = []
    for fam, h in FAMILY_HORIZON.items():
        have_dates = pv.get(fam, 0)
        units = have_dates // h
        need_ready = max(0, GATE_READY * h - have_dates)
        need_inst = max(0, GATE_INSTITUTIONAL * h - have_dates)
        if units >= GATE_INSTITUTIONAL:
            state = "INSTITUTIONAL"
        elif units >= GATE_READY:
            state = "READY_FOR_VALIDATION"
        elif have_dates == 0:
            state = "BLOCKED"
        else:
            state = "ACCUMULATING"
        out.append({
            "family": fam,
            "horizon_days": h,
            "pit_valid_dates": have_dates,
            "independent_units": units,
            "state": state,
            "gate_ready_units": GATE_READY,
            "dates_needed_for_ready": need_ready,
            "dates_needed_for_institutional": need_inst,
            "trigger": ("IF pit_valid_dates(%s) >= %d AND a multiple-testing family "
                        "can be declared AND OOS dates exist THEN %s becomes "
                        "READY_FOR_VALIDATION" % (fam, GATE_READY * h, fam)),
        })
    return out


def report(root: Path) -> dict:
    return {
        "gate_source": "backend/benchmark/report.py SIGNIFICANCE_MIN_SAMPLES=%d, "
                       "INSTITUTIONAL_MIN_SAMPLES=%d, reinterpreted in independent "
                       "DATE UNITS rather than rows" % (GATE_READY, GATE_INSTITUTIONAL),
        "markets": {
            m: {
                "ledger": ledger(root, m),
                "pit_valid_dates": pit_valid_dates(root, m),
                "triggers": triggers(root, m),
            } for m in ("india", "usa")
        },
    }
