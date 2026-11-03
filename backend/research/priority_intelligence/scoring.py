"""PIE · versioned deterministic scoring with a genuine abstention.

CEO 2026-11-03 · THE ONE THING THIS MUST NOT REPEAT
---------------------------------------------------
Phase 1 measured what R2's live classifier does: it assigns actions by
cross-sectional rank with a confidence floor 350x below the market's own
median confidence, so it returns the same 23/23/136/23/23 split on pure
float noise as on real signal. Its actionable count is a function of
universe size.

PIE must not inherit that property, so its cutoffs are ABSOLUTE and are
fitted on TRAINING folds only, then applied unchanged to the evaluation
fold. A test fold of uniformly poor names therefore yields few or no P1s
- the count moves with the quality of the names, which is the whole point
of having a classification at all. `tests/.../test_pie_scoring.py` asserts
this directly rather than leaving it as an intention.

ABSTAIN IS A VERDICT, NOT A FAILURE
-----------------------------------
A name whose available evidence weight falls below MIN_AVAILABLE_WEIGHT is
ABSTAIN. It is not scored low and it is not scored at the universe mean;
both of those would turn an absence of evidence into an opinion. Sector
and fundamentals abstain structurally for every name in this repository,
so PIE runs on at most 85% of its designed evidence and says so in every
record it writes.

CALIBRATION IS FITTED ONLY ON THE PAST
--------------------------------------
Each feature's raw value is mapped to [0,1] by its position in the
TRAINING distribution of that feature. Training folds are strictly
earlier entry dates, so the map uses no future information, and the
evaluation fold contributes nothing to its own calibration. A value more
extreme than anything in training clamps to 0 or 1 rather than
extrapolating off the end of an empirical CDF.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Mapping, Optional, Sequence

SCORING_VERSION = "pie.scoring.v1"
SCHEMA_VERSION = "1.0.0"

#: Dimension -> (weight, {feature: sign}). sign=+1 higher is better.
#: max_dd_60d and dist_52w_high are already negative numbers, so "higher
#: is better" means "shallower drawdown" and "closer to the 52w high".
DIMENSIONS: Dict[str, dict] = {
    "momentum": {"weight": 0.22, "features": {
        "ret_20d": +1, "ret_60d": +1, "ret_120d": +1}},
    "trend": {"weight": 0.22, "features": {
        "sma50_ratio": +1, "sma200_ratio": +1, "sma50_over_sma200": +1}},
    "risk": {"weight": 0.18, "features": {
        "vol_20d": -1, "max_dd_60d": +1, "dist_52w_high": +1}},
    "liquidity": {"weight": 0.08, "features": {"liquidity_20d": +1}},
    "evidence": {"weight": 0.15, "features": {
        "prior_win_rate": +1, "prior_mean_ret": +1}},
    "sector": {"weight": 0.08, "features": {"sector": +1}},
    "fundamentals": {"weight": 0.07, "features": {"fundamentals": +1}},
}

#: rsi_14 is recorded on every row but deliberately not scored: its
#: relationship to outcome is non-monotone (both extremes are
#: informative), and a non-monotone transform cannot be calibrated on 56
#: date-blocks without fitting noise. Kept as a diagnostic.
DIAGNOSTIC_ONLY = ("rsi_14",)

#: Below this share of the designed evidence weight, PIE abstains.
MIN_AVAILABLE_WEIGHT = 0.50

#: Training quantiles that become the absolute class cutoffs.
BAND_QUANTILES = {"P1": 0.80, "P2": 0.60, "WATCH": 0.40}

CLASS_P1 = "P1"
CLASS_P2 = "P2"
CLASS_WATCH = "WATCH"
CLASS_AVOID = "AVOID"
CLASS_ABSTAIN = "ABSTAIN"
ACTIONABLE_CLASSES = (CLASS_P1, CLASS_P2)


def _q(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    i = min(n - 1, max(0, int(round(p * (n - 1)))))
    return float(sorted_vals[i])


@dataclass
class Calibration:
    """Everything fitted on training folds · nothing else may be fitted."""
    version: str = SCORING_VERSION
    schema_version: str = SCHEMA_VERSION
    n_train_rows: int = 0
    n_train_dates: int = 0
    train_date_min: Optional[str] = None
    train_date_max: Optional[str] = None
    feature_grid: Dict[str, list] = field(default_factory=dict)
    bands: Dict[str, float] = field(default_factory=dict)
    n_band_rows: int = 0

    def fingerprint(self) -> str:
        """Identity of the fit · two identical fits must hash identically."""
        payload = {
            "version": self.version,
            "features": {k: [round(x, 6) for x in v]
                         for k, v in sorted(self.feature_grid.items())},
            "bands": {k: round(v, 6) for k, v in sorted(self.bands.items())},
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint()
        return d


def scored_features() -> Dict[str, int]:
    out = {}
    for spec in DIMENSIONS.values():
        out.update(spec["features"])
    return out


def fit(train_rows: Sequence[Mapping]) -> Calibration:
    """Fit feature grids on training rows · no band cutoffs yet.

    `train_rows` are dicts of {feature_name: raw_value_or_None} plus an
    `entry_date`. Rows contribute per feature: a row missing a feature
    simply does not inform that feature's distribution, rather than
    contributing a zero.
    """
    cal = Calibration()
    dates = sorted({str(r.get("entry_date"))[:10] for r in train_rows
                    if r.get("entry_date")})
    cal.n_train_rows = len(train_rows)
    cal.n_train_dates = len(dates)
    cal.train_date_min = dates[0] if dates else None
    cal.train_date_max = dates[-1] if dates else None
    for feat in sorted(scored_features()):
        vals = [float(r[feat]) for r in train_rows
                if isinstance(r.get(feat), (int, float))
                and not isinstance(r.get(feat), bool) and r[feat] == r[feat]]
        if vals:
            cal.feature_grid[feat] = sorted(vals)
    return cal


def fit_bands(cal: Calibration, train_rows: Sequence[Mapping]) -> Calibration:
    """Turn training scores into absolute class cutoffs.

    Called after `fit`, scoring the training rows with the training
    calibration. The cutoffs are then frozen numbers; the evaluation fold
    is measured against them and never re-quantiled, which is what keeps
    the P1 count a property of the names rather than of the fold size.
    """
    scores = []
    for r in train_rows:
        res = score_row(r, cal, bands=None)
        if res["pie_class"] != CLASS_ABSTAIN and res["score"] is not None:
            scores.append(float(res["score"]))
    scores.sort()
    cal.bands = {k: _q(scores, p) for k, p in BAND_QUANTILES.items()}
    cal.n_band_rows = len(scores)
    return cal


def _pct_in_grid(value: float, grid: Sequence[float]) -> float:
    """Position of `value` in the training grid, in [0,1].

    Clamped at both ends. A test value beyond everything seen in training
    scores 1.0 (or 0.0) rather than being extrapolated, because an
    empirical CDF carries no information past its own support.
    """
    n = len(grid)
    if n == 0:
        return 0.5
    if n == 1:
        return 0.5 if value == grid[0] else (1.0 if value > grid[0] else 0.0)
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if grid[mid] < value:
            lo = mid + 1
        else:
            hi = mid
    return max(0.0, min(1.0, lo / (n - 1)))


def score_row(row: Mapping, cal: Calibration,
              bands: Optional[Mapping] = "__use_cal__") -> dict:
    """Score one (ticker, date) row · deterministic given (row, cal).

    Returns the per-dimension detail as well as the total, so a reader can
    see which dimensions were present and what each contributed. Passing
    `bands=None` scores without classifying, which is how `fit_bands`
    avoids needing cutoffs before it has computed them.
    """
    use = cal.bands if bands == "__use_cal__" else bands

    dim_detail, avail_weight, weighted = {}, 0.0, 0.0
    for dname, spec in DIMENSIONS.items():
        parts = []
        for feat, sign in spec["features"].items():
            v = row.get(feat)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v != v:
                continue
            grid = cal.feature_grid.get(feat)
            if not grid:
                continue
            p = _pct_in_grid(float(v), grid)
            parts.append(p if sign > 0 else 1.0 - p)
        if parts:
            d = sum(parts) / len(parts)
            dim_detail[dname] = {"score": round(d, 6),
                                 "n_features": len(parts),
                                 "weight": spec["weight"],
                                 "available": True}
            avail_weight += spec["weight"]
            weighted += spec["weight"] * d
        else:
            dim_detail[dname] = {"score": None, "n_features": 0,
                                 "weight": spec["weight"], "available": False}

    total_weight = sum(s["weight"] for s in DIMENSIONS.values())
    if avail_weight < MIN_AVAILABLE_WEIGHT:
        return {
            "score": None, "pie_class": CLASS_ABSTAIN,
            "available_weight": round(avail_weight, 6),
            "designed_weight": round(total_weight, 6),
            "abstain_reason": "AVAILABLE_WEIGHT_%.2f_BELOW_%.2f" % (
                avail_weight, MIN_AVAILABLE_WEIGHT),
            "dimensions": dim_detail, "scoring_version": SCORING_VERSION,
        }

    score = weighted / avail_weight
    out = {
        "score": round(score, 6), "pie_class": None,
        "available_weight": round(avail_weight, 6),
        "designed_weight": round(total_weight, 6),
        "abstain_reason": None,
        "dimensions": dim_detail, "scoring_version": SCORING_VERSION,
    }
    if use is None:
        return out
    if score >= use.get("P1", 1.1):
        out["pie_class"] = CLASS_P1
    elif score >= use.get("P2", 1.1):
        out["pie_class"] = CLASS_P2
    elif score >= use.get("WATCH", 1.1):
        out["pie_class"] = CLASS_WATCH
    else:
        out["pie_class"] = CLASS_AVOID
    return out


def class_counts(results: Sequence[Mapping]) -> dict:
    out = {c: 0 for c in (CLASS_P1, CLASS_P2, CLASS_WATCH,
                          CLASS_AVOID, CLASS_ABSTAIN)}
    for r in results:
        k = r.get("pie_class")
        if k in out:
            out[k] += 1
    out["n"] = len(results)
    out["n_actionable"] = out[CLASS_P1] + out[CLASS_P2]
    out["actionable_share"] = (round(out["n_actionable"] / len(results), 4)
                               if results else 0.0)
    return out
