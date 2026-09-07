"""AEGIS · R3-1A · FROZEN BASELINE-REPLICATION TARGET.

CEO 2026-09-07 · resolve the horizon question BEFORE R3-3, so the
replication gate cannot pass or fail on an unresolved choice rather than
on R3's actual quality.

THE FINDING THAT SETTLES IT
---------------------------
The question was posed as "USA fwd_5d 31.7% vs fwd_10d 61.5%, same
n = 546". Mining the existing artifact
(`reports/research/mr_forward_validation_{market}.json`) shows the
horizons do NOT share n. 546 is the COHORT size; each horizon has its own
measured n, because longer horizons have not closed yet:

    USA    fwd_1d  n=533  37.71%  CI [33.70, 41.90]
           fwd_3d  n=101  40.59%  CI [31.53, 50.35]
           fwd_5d  n=101  31.68%  CI [23.42, 41.29]
           fwd_10d n= 13  61.54%  CI [35.52, 82.29]   <-- 13 observations
           fwd_20d n=  0     —

    INDIA  fwd_1d  n= 61  26.23%  CI [16.84, 38.44]
           fwd_3d  n= 59  37.29%  CI [26.08, 50.05]
           fwd_5d  n= 54  38.89%  CI [27.04, 52.21]
           fwd_10d n= 52  26.92%  CI [16.77, 40.25]
           fwd_20d n=  0     —

The USA 10d confidence interval [35.52, 82.29] OVERLAPS the 5d interval
[23.42, 41.29]. The two are not statistically distinguishable, so the
apparent "horizon effect" is a small-sample artifact, not a signal. India
shows no monotone horizon story either (26.2 / 37.3 / 38.9 / 26.9).

RESOLUTION
----------
fwd_5d is the only horizon at validation_candidate sample size (>=50) in
BOTH markets (USA 101, India 54). It is therefore the frozen primary
replication target. fwd_10d is reported as SECONDARY: usable for India
(n=52) but hypothesis-tier for USA (n=13), so it may not carry a gate
verdict. fwd_20d has no closed observations in either market.

This is deliberately a PARAMETER, not a constant buried in the gate. When
accumulation lifts fwd_10d/20d above the tier threshold, re-run
`resolve()` and re-freeze rather than editing a gate by hand.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Locked sample-size tiers (AEGIS governance).
TIERS = ((0, "no_data"), (1, "observation"), (5, "hypothesis"),
         (15, "research_signal"), (30, "stronger_evidence"),
         (50, "validation_candidate"))

MIN_TIER_FOR_GATE = 50          # validation_candidate · may carry a verdict
CANDIDATE_HORIZONS = (1, 3, 5, 10, 20)

# ── FROZEN TARGET · R3-1A · 2026-09-07 ────────────────────────────────
FROZEN = {
    "frozen_on": "2026-09-07",
    "primary_horizon_days": 5,
    "secondary_horizons_days": [10],
    "markets": ["india", "usa"],
    "cohort": "cohort_ALL",          # first-entry, non-administrative
    "comparator": "R2",
    "metric": "information_coefficient",
    "tolerance": 0.02,
    "rationale": (
        "fwd_5d is the only horizon at validation_candidate n (>=50) in both "
        "markets (USA 101 · India 54). USA fwd_10d n=13 with CI [35.52, "
        "82.29] overlaps fwd_5d CI [23.42, 41.29], so the apparent 5d-vs-10d "
        "difference is a small-sample artifact, not a horizon effect."),
    "evidence_source": "reports/research/mr_forward_validation_{market}.json",
}


def tier_for(n: Optional[int]) -> str:
    if not n:
        return "no_data"
    label = "no_data"
    for threshold, name in TIERS:
        if n >= threshold:
            label = name
    return label


def resolve(root: Path) -> dict:
    """Recompute horizon evidence from the existing artifact.

    Pure measurement · no new infrastructure, exactly as directed. Returns
    per-market per-horizon n / win-rate / CI / tier plus which horizons are
    currently eligible to carry a gate verdict.
    """
    out = {"frozen": FROZEN, "measured": {}, "eligible_for_gate": {}}
    for market in FROZEN["markets"]:
        p = root / "reports" / "research" / f"mr_forward_validation_{market}.json"
        if not p.exists():
            out["measured"][market] = {"status": "ARTIFACT_ABSENT", "path": str(p)}
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        cohort = d.get(FROZEN["cohort"]) or {}
        rows, eligible = {}, []
        for h in CANDIDATE_HORIZONS:
            n = cohort.get(f"fwd_{h}d_n")
            rows[f"fwd_{h}d"] = {
                "n": n,
                "win_rate_pct": cohort.get(f"fwd_{h}d_win_rate_pct"),
                "win_rate_ci": cohort.get(f"fwd_{h}d_win_rate_ci"),
                "avg_pct": cohort.get(f"fwd_{h}d_avg"),
                "tier": tier_for(n),
            }
            if n and n >= MIN_TIER_FOR_GATE:
                eligible.append(h)
        out["measured"][market] = {
            "status": "OK",
            "cohort_n_observations": d.get("n_observations"),
            "horizons": rows,
        }
        out["eligible_for_gate"][market] = eligible
    # A horizon may carry the gate only where it is eligible in EVERY market
    # we intend to gate on · otherwise the verdict is market-dependent.
    sets = [set(v) for v in out["eligible_for_gate"].values()]
    out["eligible_in_all_markets"] = sorted(set.intersection(*sets)) if sets else []
    out["primary_is_eligible"] = (
        FROZEN["primary_horizon_days"] in out["eligible_in_all_markets"])
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3-1A horizon resolution")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    print(json.dumps(resolve(root), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
