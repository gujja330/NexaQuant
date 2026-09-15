"""Forward evidence accumulation clock.

Counts what AEGIS can actually testify to, in INDEPENDENT DATE UNITS.

Rows and tickers are not evidence. 516 USA names on one date is one date, not
516 observations: the admitted set overlaps ~71% day to day and daily mean
returns carry lag-1 autocorrelation ~0.64, so overlapping windows are counted
as one unit per horizon, not one per row.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.memory.daily_snapshot import ROOT_DIRNAME, PIT_OK, PIT_PARTIAL

# Minimum independent units before a family is worth testing at all.
# Derived from the 2026-09-15 gate: India's rejected severe-loss result sat on
# ~5 units, and its apparent +1.825pp uplift was one month. 12 is the floor at
# which leave-one-period-out can remove any single month and still leave a
# testable remainder.
MIN_UNITS_TO_TEST = 12


def sealed_days(root: Path, market: str) -> list[str]:
    d = Path(root) / ROOT_DIRNAME / market.lower()
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir()
                  if p.is_dir() and (p / "SEALED").exists())


def clock(root: Path, market: str) -> dict:
    days = sealed_days(root, market)
    n = len(days)
    cov: dict[str, int] = {}
    for a in days:
        s = json.loads((Path(root) / ROOT_DIRNAME / market.lower() / a /
                        "snapshot.json").read_text(encoding="utf-8"))
        for fam, p in s.get("provenance", {}).items():
            if p.get("pit_status") in (PIT_OK, PIT_PARTIAL):
                cov[fam] = cov.get(fam, 0) + 1
    return {
        "market": market.lower(),
        "sealed_days": n,
        "span": [days[0], days[-1]] if days else None,
        "effective_units": {
            # non-overlapping blocks: a h-day horizon consumes h dates
            "5d": n // 5, "10d": n // 10, "20d": n // 20,
        },
        "family_coverage_days": dict(sorted(cov.items())),
        "min_units_to_test": MIN_UNITS_TO_TEST,
        "testable_at_5d": (n // 5) >= MIN_UNITS_TO_TEST,
        "note": ("counted in independent date units; rows and tickers are not "
                 "independent evidence"),
    }


def readiness(root: Path) -> dict:
    """Part I. Which families become testable, and how many more dates are needed.

    No models are run. This reports distance-to-testable only.
    """
    ind, usa = clock(root, "india"), clock(root, "usa")

    def need(c: dict, horizon: str = "5d") -> int:
        have = c["effective_units"][horizon]
        return max(0, (MIN_UNITS_TO_TEST - have) * int(horizon.rstrip("d")))

    fams = [
        ("sector", "ACCUMULATE", "PIT_OK both markets (git provenance)",
         "sector_* features are computed but India's map never reaches the rows"),
        ("cap", "REJECTED", "India PIT_BLOCKED (no cap column); USA PIT_PARTIAL",
         "cap hypothesis already rejected; substrate would only allow a re-test"),
        ("fundamentals", "ACCUMULATE", "India PIT_BLOCKED; USA PIT_PARTIAL (ingestion only)",
         "India can never be back-filled; USA accrues from 2026-07-20"),
        ("earnings", "BLOCKED", "India PIT_BLOCKED (forward field only); USA PIT_PARTIAL",
         "needs announcement timing, which no source provides for India"),
        ("macro", "ACCUMULATE", "USA PIT_OK (levels); India PIT_BLOCKED",
         "USA unblocked 2026-09-15; India source file does not exist"),
        ("cross_sector", "BLOCKED", "depends on sector + macro",
         "blocked until both are PIT_OK and accumulated"),
        ("relational", "REJECTED", "peer lead/lag did not survive FDR",
         "do not reopen without a new mandate"),
        ("survival", "BLOCKED", "53 events over ~5 units supports 1.1 covariates",
         "needs events AND independent units, plus separable competing risks"),
        ("r3", "NOT_RATED", "no component earned promotion",
         "gated on every other family"),
    ]
    out = []
    for name, status, pit, note in fams:
        out.append({
            "family": name, "evidence_status": status, "pit_status": pit,
            "india_more_dates_needed_5d": need(ind),
            "usa_more_dates_needed_5d": need(usa),
            "production_relevance": note,
        })
    return {"india": ind, "usa": usa, "families": out,
            "rule": "no family is testable below %d independent units" % MIN_UNITS_TO_TEST}
