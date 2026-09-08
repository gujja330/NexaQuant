"""MR RESPONSE CURVES · 7B / 7C / 7D · CEO 2026-09-08.

> "Don't fit a single linear 'higher MA200 distance = better' rule. We need
>  to test ZONES, not direction."

WHY THIS EXISTS
---------------
The V1 confirmatory run compared the loser decile against the winner
decile with a rank test. That answers "do the two tails differ?" but not
"where in the feature space is it safe, and where is it dangerous?" - and
a rank test is blind to a non-monotonic response, which is exactly what
the V1 means suggested:

    trend_ma200_dist   India losers -2.59 / winners +0.84
                       USA   losers +16.16 / winners +6.61

Same variable, opposite sign by market. That is not "trend is good". It
is consistent with trend PARTICIPATION helping and trend EXTENSION
hurting, with the two markets sitting on opposite sides of the curve. A
linear test cannot see that; a binned response curve can.

CONFIDENCE IS THE OTHER REASON
------------------------------
Confidence failed to separate the tails in both markets and pointed the
WRONG way (losers had higher mean confidence). Before concluding it is
non-predictive, the CEO's alternatives have to be ruled out: predictive
only in a sub-range, interacting with trend or volatility, or simply
miscalibrated. A decile response curve distinguishes "useless" from
"useful only in part of its range".

STATUS · EXPLORATORY
--------------------
Family: MR_DEPENDENCY_EXPLORATORY_60D_V1.

These curves are hypothesis-generating. Bin boundaries were chosen by the
CEO before the run, but the curves are not part of the corrected
confirmatory family and no bin may become a production rule on this
evidence. Cells are labelled with the standard sample-size tiers so a
3-observation bin is never read as a finding.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.mr_response_curves.v1"
FAMILY = "MR_DEPENDENCY_EXPLORATORY_60D_V1"

HORIZONS = ["fwd_5d_pct", "fwd_10d_pct"]

# CEO-specified bins · frozen before the run.
CONFIDENCE_BINS = [(None, 55), (55, 60), (60, 65), (65, 70), (70, 75),
                   (75, 80), (80, 85), (85, 90), (90, None)]
MA200_ZONES = [(None, -20), (-20, -10), (-10, -5), (-5, 0), (0, 5),
               (5, 10), (10, 20), (20, None)]

TIERS = ((5, "OBSERVATION"), (15, "HYPOTHESIS"), (30, "RESEARCH_SIGNAL"),
         (50, "STRONGER_EVIDENCE"))


def tier(n: int) -> str:
    for cap, name in TIERS:
        if n < cap:
            return name
    return "VALIDATION_CANDIDATE"


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _label(lo, hi, unit="") -> str:
    if lo is None:
        return f"<{hi}{unit}"
    if hi is None:
        return f">={lo}{unit}"
    return f"{lo}..{hi}{unit}"


def _bin_of(v, bins):
    if v is None:
        return None
    for lo, hi in bins:
        if (lo is None or v >= lo) and (hi is None or v < hi):
            return _label(lo, hi)
    return None


def _cell(rows: list, horizon: str) -> dict:
    """Everything the CEO asked per bin · n, expectancy, median, win rate,
    mean winner, mean loser, P10/P90, MAE, MFE, stop-hit."""
    vals = [_num(r.get(horizon)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)
    wins = [v for v in s if v > 0]
    losses = [v for v in s if v < 0]

    def q(p):
        return s[min(n - 1, max(0, int(n * p)))]

    def mean_of(key):
        xs = [_num(r.get(key)) for r in rows]
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 3) if xs else None
    hits = [r for r in rows if r.get("stop_hit_within_20d") is not None]
    return {
        "n": n, "tier": tier(n),
        "expectancy_pct": round(sum(s) / n, 3),
        "median_pct": round(s[n // 2], 3),
        "win_rate_pct": round(len(wins) / n * 100, 1),
        "mean_winner_pct": round(sum(wins) / len(wins), 3) if wins else None,
        "mean_loser_pct": round(sum(losses) / len(losses), 3) if losses else None,
        "p10_pct": round(q(0.10), 3), "p90_pct": round(q(0.90), 3),
        "worst_pct": round(s[0], 3),
        "mae_pct": mean_of("mae_pct"), "mfe_pct": mean_of("mfe_pct"),
        "stop_hit_pct": (round(sum(1 for r in hits
                                   if r.get("stop_hit_within_20d")) / len(hits)
                               * 100, 1) if hits else None),
    }


def _curve(rows: list, keyfn, bins, horizon: str) -> dict:
    buckets = {}
    for r in rows:
        b = _bin_of(keyfn(r), bins)
        if b:
            buckets.setdefault(b, []).append(r)
    order = [_label(lo, hi) for lo, hi in bins]
    return {b: _cell(buckets[b], horizon) for b in order if b in buckets}


def _vol_tercile(rows: list) -> None:
    vals = sorted(v for v in (_num(r.get("vol_20d_pct")) for r in rows)
                  if v is not None)
    if not vals:
        return
    lo, hi = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    for r in rows:
        v = _num(r.get("vol_20d_pct"))
        r["_vol_tercile"] = (None if v is None else
                             "VOL_LOW" if v <= lo else
                             "VOL_MID" if v <= hi else "VOL_HIGH")


def analyse(root: Path, market: str) -> dict:
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}
    _vol_tercile(rows)

    conf = lambda r: _num(r.get("confidence_pct"))          # noqa: E731
    ma200 = lambda r: _num(r.get("ma200_dist_pct"))         # noqa: E731

    out = {}
    for h in HORIZONS:
        pop = [r for r in rows if _num(r.get(h)) is not None]
        if len(pop) < 30:
            continue
        # 7D · two interactions only. The CEO capped this deliberately:
        # "Not 20 interactions."
        inter_cm, inter_cv = {}, {}
        for r in pop:
            cb, zb = _bin_of(conf(r), CONFIDENCE_BINS), _bin_of(ma200(r), MA200_ZONES)
            if cb and zb:
                inter_cm.setdefault(f"{cb} | {zb}", []).append(r)
            if cb and r.get("_vol_tercile"):
                inter_cv.setdefault(f"{cb} | {r['_vol_tercile']}", []).append(r)
        out[h] = {
            "population": _cell(pop, h),
            "confidence_curve": _curve(pop, conf, CONFIDENCE_BINS, h),
            "ma200_zone_curve": _curve(pop, ma200, MA200_ZONES, h),
            "confidence_x_ma200": {k: _cell(v, h)
                                   for k, v in sorted(inter_cm.items())
                                   if len(v) >= 15},
            "confidence_x_volatility": {k: _cell(v, h)
                                        for k, v in sorted(inter_cv.items())
                                        if len(v) >= 15},
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": ("EXPLORATORY · hypothesis-generating only · no bin may "
                   "become a production rule on this evidence"),
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_cohort": len(rows),
        "bins": {"confidence": [_label(a, b) for a, b in CONFIDENCE_BINS],
                 "ma200_zone": [_label(a, b) for a, b in MA200_ZONES]},
        "results": out,
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "cohort"
            / f"mr_response_curves_{market.lower()}.json")


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="MR response curves 7B/7C/7D")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in ("india", "usa"):
        rep = analyse(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        p = emit(root, rep)
        print(f"response_curves:{m} · n={rep['n_cohort']} -> "
              f"{p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
