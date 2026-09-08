"""ML DISCOVERY v1 · TEMPORAL FEATURES · CEO 2026-09-08.

> "Does a feature become predictive only after a particular lag, and does
>  that relationship persist across different forward horizons?"

TWO SOURCES OF LAG · WITH VERY DIFFERENT AVAILABILITY
------------------------------------------------------
Measured on the actual cohort before building anything:

  COHORT-derived (confidence, rank - model outputs stored per prediction)
      India   t-1 45/45 · t-3 32 · t-5 33 · t-10 30 · t-20 22
      USA     t-1 498/498 · t-3 25 · t-5 16 · t-10 13 · t-20 16

  PRICE-derived (MA distance, momentum, volatility - recomputable)
      ~1,411 bars per India ticker · ~1,255 per USA ticker

So USA model-feature lags beyond t-1 do not exist and must not be
fabricated: 16 of 498 tickers is not a feature, it is a hole. Price-derived
lags are available at any depth in both markets.

The builder therefore computes what is computable, MEASURES coverage per
lag, and DROPS any lag below the floor rather than emitting a column that
is 97% NaN and letting a tree quietly split on the 3% that remain.

PIT DISCIPLINE · THE PROPERTY THAT MATTERS MOST
-----------------------------------------------
Every price-derived lag uses ONLY bars dated <= the prediction date. A
lag feature is the one place where lookahead is easiest to introduce and
hardest to see: shifting the wrong way silently hands the model tomorrow's
price. `test_price_lags_never_see_the_future` pins it.

MULTI-HORIZON TARGETS
---------------------
fwd 1d / 3d / 5d / 10d / 20d, plus the two the CEO asked for:

  consensus   positive at 5d AND 10d · agreement across horizons
  divergence  positive at 5d but negative at 20d · early gain that
              reverses, which is an EXIT question, not an entry one

USA fwd_20d has not matured, so any target needing it is unavailable
there and is reported as such rather than silently skipped.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.temporal.v1"

LAGS = [1, 2, 3, 5, 10, 20]
ROLL_WINDOWS = [3, 5, 10, 20, 60]
HORIZONS = ["fwd_1d_pct", "fwd_3d_pct", "fwd_5d_pct", "fwd_10d_pct",
            "fwd_20d_pct"]

# A lag column must reach this share of rows or it is dropped entirely.
MIN_LAG_COVERAGE_PCT = 60.0


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


# ── price series ────────────────────────────────────────────────────────

def _price_path(root: Path, market: str, ticker: str) -> Optional[Path]:
    t = str(ticker).upper().split(".", 1)[0]
    if market == "usa":
        p = root / "usa" / "data" / "raw" / "us" / f"{t}_D1.parquet"
    else:
        p = root / "data" / "raw" / "india" / f"{t}_D1.parquet"
    return p if p.exists() else None


def _load_series(root: Path, market: str, ticker: str):
    """(dates, closes) ascending · None when unavailable."""
    import pandas as pd
    p = _price_path(root, market, ticker)
    if p is None:
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    if isinstance(df.index, pd.DatetimeIndex):
        idx = [d.date() for d in df.index]
    else:
        col = next((c for c in df.columns if c.lower() in ("date", "datetime")),
                   None)
        if col is None:
            return None
        idx = [pd.to_datetime(v).date() for v in df[col]]
    ccol = next((c for c in df.columns if c.lower() == "close"), None)
    if ccol is None:
        return None
    pairs = sorted(zip(idx, [_num(v) for v in df[ccol]]))
    pairs = [(d, c) for d, c in pairs if c is not None]
    if not pairs:
        return None
    return [d for d, _ in pairs], [c for _, c in pairs]


def price_features(dates, closes, asof: date, lags=LAGS,
                   windows=ROLL_WINDOWS) -> dict:
    """PIT-SAFE. Uses only bars with date <= asof.

    `hi` is the index of the last bar at or before the prediction date;
    everything is indexed backwards from there, so no computation can
    reach a bar the predictor could not have seen.
    """
    hi = -1
    for i, d in enumerate(dates):
        if d <= asof:
            hi = i
        else:
            break
    if hi < 0:
        return {}
    out = {}
    px = closes[hi]

    for k in lags:
        j = hi - k
        out[f"ret_lag_{k}d"] = (round((px / closes[j] - 1.0) * 100, 4)
                                if j >= 0 and closes[j] else None)
    for w in windows:
        j = hi - w + 1
        if j < 0:
            out[f"roll_mean_{w}d"] = None
            out[f"roll_vol_{w}d"] = None
            out[f"dist_ma_{w}d"] = None
            continue
        win = closes[j:hi + 1]
        mean = sum(win) / len(win)
        var = sum((c - mean) ** 2 for c in win) / max(1, len(win) - 1)
        sd = math.sqrt(var)
        out[f"roll_mean_{w}d"] = round(mean, 4)
        out[f"roll_vol_{w}d"] = round(sd / mean * 100, 4) if mean else None
        out[f"dist_ma_{w}d"] = round((px / mean - 1.0) * 100, 4) if mean else None

    # Second-order structure · the CEO asked specifically for expansion /
    # contraction and slope, not just levels.
    v5, v20 = out.get("roll_vol_5d"), out.get("roll_vol_20d")
    out["vol_expansion_5_20"] = (round(v5 / v20, 4)
                                 if v5 and v20 else None)
    m20 = out.get("dist_ma_20d")
    j = hi - 10
    if j >= 0 and m20 is not None:
        w0 = closes[max(0, j - 19):j + 1]
        if w0:
            mean0 = sum(w0) / len(w0)
            prev = (closes[j] / mean0 - 1.0) * 100 if mean0 else None
            out["ma20_dist_slope_10d"] = (round(m20 - prev, 4)
                                          if prev is not None else None)
    out.setdefault("ma20_dist_slope_10d", None)

    r1, r5 = out.get("ret_lag_1d"), out.get("ret_lag_5d")
    out["momentum_persistence_1_5"] = (
        round(r1 / r5, 4) if (r1 is not None and r5) else None)
    return out


# ── cohort-derived lags ─────────────────────────────────────────────────

def cohort_lags(rows: list, fields=("confidence_pct", "rank"),
                lags=LAGS) -> None:
    """Attach prior observations of MODEL outputs for the same ticker.

    Only exact-lag matches within +/-1 calendar day are used. USA has
    2.2 observations per ticker, so most of these will be missing - that
    is the point, and the coverage report is what decides whether the
    column survives.
    """
    by = defaultdict(list)
    for r in rows:
        d = _d(r.get("prediction_date"))
        if d:
            by[str(r.get("ticker"))].append((d, r))
    for t in by:
        by[t].sort(key=lambda kv: kv[0])
    for r in rows:
        d = _d(r.get("prediction_date"))
        if not d:
            continue
        hist = by[str(r.get("ticker"))]
        for k in lags:
            match = None
            for dd, rr in hist:
                if abs((d - dd).days - k) <= 1:
                    match = rr
                    break
            for f in fields:
                r[f"{f}_lag_{k}d"] = _num(match.get(f)) if match else None
        # Change since the most recent prior observation · cheap, and the
        # CEO called out "confidence change" explicitly.
        prior = [rr for dd, rr in hist if dd < d]
        for f in fields:
            now, was = _num(r.get(f)), (_num(prior[-1].get(f)) if prior else None)
            r[f"{f}_change"] = (round(now - was, 4)
                                if (now is not None and was is not None)
                                else None)


def attach(root: Path, market: str, rows: list) -> dict:
    """Attach all temporal features · returns the coverage report."""
    cohort_lags(rows)
    cache = {}
    for r in rows:
        t = str(r.get("ticker") or "")
        d = _d(r.get("prediction_date"))
        if not t or not d:
            continue
        if t not in cache:
            cache[t] = _load_series(root, market, t)
        s = cache[t]
        if s is None:
            continue
        for k, v in price_features(s[0], s[1], d).items():
            r[k] = v

    names = set()
    for r in rows:
        names |= {k for k in r
                  if k.startswith(("ret_lag_", "roll_", "dist_ma_",
                                   "vol_expansion", "ma20_dist_slope",
                                   "momentum_persistence"))
                  or "_lag_" in k or k.endswith("_change")}
    n = len(rows) or 1
    cov = {}
    for k in sorted(names):
        present = sum(1 for r in rows if _num(r.get(k)) is not None)
        cov[k] = {"coverage_pct": round(present / n * 100, 1),
                  "usable": present / n * 100 >= MIN_LAG_COVERAGE_PCT}
    dropped = [k for k, v in cov.items() if not v["usable"]]
    for r in rows:
        for k in dropped:
            r.pop(k, None)
    return {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "n_rows": len(rows),
        "min_coverage_pct": MIN_LAG_COVERAGE_PCT,
        "n_generated": len(names),
        "n_usable": len(names) - len(dropped),
        "n_dropped_low_coverage": len(dropped),
        "dropped": dropped,
        "coverage": cov,
        "usable_features": sorted(k for k, v in cov.items() if v["usable"]),
    }


# ── multi-horizon targets ───────────────────────────────────────────────

def horizon_targets(rows: list) -> dict:
    """Availability per horizon plus consensus / divergence labels."""
    avail = {h: sum(1 for r in rows if _num(r.get(h)) is not None)
             for h in HORIZONS}
    for r in rows:
        f5, f10 = _num(r.get("fwd_5d_pct")), _num(r.get("fwd_10d_pct"))
        f20 = _num(r.get("fwd_20d_pct"))
        r["target_consensus_5_10"] = (
            (1.0 if (f5 > 0 and f10 > 0) else 0.0)
            if (f5 is not None and f10 is not None) else None)
        r["target_divergence_5_20"] = (
            (1.0 if (f5 > 0 and f20 < 0) else 0.0)
            if (f5 is not None and f20 is not None) else None)
    n = len(rows) or 1
    return {
        "horizon_availability": avail,
        "horizon_available_pct": {h: round(v / n * 100, 1)
                                  for h, v in avail.items()},
        "consensus_5_10_n": sum(1 for r in rows
                                if r.get("target_consensus_5_10") is not None),
        "divergence_5_20_n": sum(1 for r in rows
                                 if r.get("target_divergence_5_20") is not None),
        "unavailable_horizons": [h for h, v in avail.items() if v == 0],
    }
