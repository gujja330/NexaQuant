"""R2 admission-cohort outcome baseline · what happened AFTER admission.

WHAT THIS IS
------------
The first reproducible measurement of the R2 admission cohort using
resolved, point-in-time outcomes from `outcome_resolver`. It is the
baseline every future R3 specialist must beat.

WHAT THIS IS NOT
----------------
**It is not R3 performance.** R3 abstained on all 1,724 India and 2,300
USA observations - TAKE 0, AVOID 0 - so it expressed no view on any of
them. The prior abstention counterfactual showed that declining to trade
beat a losing cohort; that describes R2's returns, not R3 discrimination.

Labelling this "R3 results" would be the single most misleading thing
this programme could do, so the module reports the cohort it actually
measures: R2 admissions.

DISCIPLINE
----------
* an UNRESOLVED horizon is excluded, never counted as a 0% return.
  Coverage is reported alongside every statistic so a thin sample cannot
  masquerade as a result.
* inference is over ADMISSION DATES, not rows. 116 trades across 30
  dates are not 116 independent observations - every name admitted on
  one morning shares that morning's market.
* benchmark is matched per position over its own holding window, close
  to close from the bar AFTER admission.
* repeated tickers are counted and reported; a name admitted three times
  contributes three correlated observations.
* transaction costs are an ASSUMPTION, labelled as such, applied as a
  round-trip haircut. No actual fills exist in this data.
"""
from __future__ import annotations

import json
import random
import statistics as st
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.cohort_baseline.v1"

HORIZONS = (5, 10, 20)

# Declared up front. Not a measured cost - there are no fills in this data.
ASSUMED_ROUNDTRIP_COST_PCT = 0.20
COST_GRID_PCT = (0.0, 0.10, 0.20, 0.50)

# The programme's floor for a confirmatory read. Below it a result is
# EXPLORATORY regardless of how the numbers look.
MIN_DATES_CONFIRMATORY = 20
N_BOOTSTRAP = 2000
SEED = 20261027

BENCH = {"india": "data/raw/india/NSEI_D1.parquet",
         "usa": "usa/data/raw/us/_IDX_GSPC_D1.parquet"}

_bench_cache: dict = {}


def _bench_frame(root: Path, market: str) -> Optional[pd.DataFrame]:
    if market in _bench_cache:
        return _bench_cache[market]
    p = Path(root) / BENCH[market]
    d = None
    if p.exists():
        try:
            d = pd.read_parquet(p)
            d.index = pd.to_datetime(d.index)
            d = d.sort_index()
            d.columns = [c.lower() for c in d.columns]
        except Exception:
            d = None
    _bench_cache[market] = d
    return d


def _bench_fwd(df: Optional[pd.DataFrame], asof: str, horizon: int):
    """Benchmark over the same window · from the bar AFTER asof."""
    if df is None:
        return None
    w = df[df.index > pd.Timestamp(asof)]
    if len(w) < 2 or len(w) - 1 < horizon:
        return None
    a = float(w["close"].iloc[0])
    b = float(w["close"].iloc[horizon])
    return 100.0 * (b - a) / a if a else None


def admissions(root: Path, market: str) -> list:
    """R2 ADMISSION decisions only (`r2_signal == NEW`).

    ACTIVE / ACTIVE+ observations are positions already held. Including
    them would inflate the sample with non-decisions - India has 1,557
    ACTIVE+ against 143 NEW.
    """
    from backend.research.r3_program import shadow
    out = []
    for r in shadow.load_ledger(Path(root), market):
        if str(r.get("r2_signal")) != "NEW":
            continue
        asof = str(r.get("as_of") or "")[:10]
        tic = str(r.get("ticker") or "").upper().replace(".NS", "")
        if asof and tic:
            out.append({"as_of": asof, "ticker": tic})
    return out


def _outcomes(root: Path, market: str) -> dict:
    from backend.research.r3_program import outcome_resolver as orr
    p = orr.outcomes_path(Path(root), market)
    by = {}
    if not p.exists():
        return by
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            o = json.loads(line)
            by[(o["as_of"], o["ticker"], int(o["horizon_days"]))] = o["fwd_pct"]
        except Exception:
            continue
    return by


def _stats(v: list) -> dict:
    if not v:
        return {"n": 0}
    s = sorted(v)
    n = len(s)
    w = [x for x in s if x > 0]
    return {
        "n": n,
        "mean_pct": round(st.mean(s), 4),
        "median_pct": round(st.median(s), 4),
        "stdev_pct": round(st.stdev(s), 4) if n > 1 else None,
        "win_rate_pct": round(100.0 * len(w) / n, 1),
        "loss_rate_pct": round(100.0 * (n - len(w)) / n, 1),
        "mean_win_pct": round(st.mean(w), 4) if w else None,
        "mean_loss_pct": (round(st.mean([x for x in s if x <= 0]), 4)
                          if n - len(w) else None),
        "worst_pct": round(s[0], 4),
        "best_pct": round(s[-1], 4),
        "p05_pct": round(s[max(0, int(0.05 * n) - 1)], 4),
        "p95_pct": round(s[min(n - 1, int(0.95 * n))], 4),
        "sum_pp": round(sum(s), 2),
    }


def evaluate(root: Path, market: str) -> dict:
    root = Path(root)
    adm = admissions(root, market)
    out = _outcomes(root, market)
    bdf = _bench_frame(root, market)

    tickers = [a["ticker"] for a in adm]
    repeats = {t: tickers.count(t) for t in set(tickers) if tickers.count(t) > 1}

    rep = {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "generated_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "production_authority": False,
        "cohort": "R2 ADMISSIONS (r2_signal == NEW)",
        "NOT": ("This is NOT R3 performance. R3 abstained on every "
                "observation (TAKE 0 / AVOID 0) and expressed no view on "
                "any of these admissions."),
        "n_admissions": len(adm),
        "n_unique_tickers": len(set(tickers)),
        "n_admission_dates": len({a["as_of"] for a in adm}),
        "repeated_tickers": dict(sorted(repeats.items(),
                                        key=lambda kv: -kv[1])[:12]),
        "assumed_roundtrip_cost_pct": ASSUMED_ROUNDTRIP_COST_PCT,
        "cost_is_an_assumption": True,
        "horizons": {},
    }
    if adm:
        ds = sorted({a["as_of"] for a in adm})
        rep["date_range"] = [ds[0], ds[-1]]

    for h in HORIZONS:
        rows, unresolved = [], 0
        for a in adm:
            v = out.get((a["as_of"], a["ticker"], h))
            if v is None:
                unresolved += 1
                continue
            b = _bench_fwd(bdf, a["as_of"], h)
            rows.append({"as_of": a["as_of"], "ticker": a["ticker"],
                         "r": float(v), "b": b})
        got = [r["r"] for r in rows]
        matched = [r for r in rows if r["b"] is not None]
        alpha = [r["r"] - r["b"] for r in matched]

        blk = {
            "n_eligible": len(adm),
            "n_resolved": len(rows),
            "n_unresolved": unresolved,
            "coverage_pct": (round(100.0 * len(rows) / len(adm), 1)
                             if adm else 0.0),
            "n_admission_dates_resolved": len({r["as_of"] for r in rows}),
            "strategy": _stats(got),
            "benchmark": _stats([r["b"] for r in matched]),
            "alpha": _stats(alpha),
            "n_benchmark_matched": len(matched),
            "beat_benchmark_pct": (round(100.0 * sum(1 for x in alpha if x > 0)
                                         / len(alpha), 1) if alpha else None),
            "net_of_assumed_cost": (
                {"mean_pct": round(st.mean(got) - ASSUMED_ROUNDTRIP_COST_PCT,
                                   4),
                 "note": "ASSUMED %.2f%% round-trip · no actual fills exist"
                         % ASSUMED_ROUNDTRIP_COST_PCT}
                if got else None),
        }
        # ── date-level aggregation ──────────────────────────────────
        # Two different questions, and conflating them is how a cohort
        # flatters itself:
        #
        #   row-level   what did the average admitted POSITION return?
        #               -> the equal-weighted book's actual result
        #   date-level  what did the average admission DAY return?
        #               -> the correct unit for INFERENCE, because every
        #                  name admitted one morning shares that morning
        #
        # India 5d: row -0.124% vs date -0.904%. The gap is real and has a
        # cause - corr(n_admissions_on_date, date_mean) = +0.233, so busy
        # days did better and equal-weighting dates upweights the thin bad
        # ones. 13 of 28 dates carry a single admission.
        #
        # Neither number is "the" answer. Both are reported, plus the
        # n-weighted date mean which recovers the row-level figure.
        if rows:
            byd = {}
            for r in rows:
                byd.setdefault(r["as_of"], []).append(r["r"])
            dkeys = sorted(byd)
            dm = [st.mean(byd[d]) for d in dkeys]
            ns = [len(byd[d]) for d in dkeys]
            singles = sum(1 for n in ns if n == 1)
            wmean = sum(m * n for m, n in zip(dm, ns)) / sum(ns)

            rnd = random.Random(SEED)
            boots = []
            for _ in range(N_BOOTSTRAP):
                pick = [rnd.choice(dkeys) for _ in dkeys]
                vals = [x for d in pick for x in byd[d]]
                if vals:
                    boots.append(st.mean(vals))
            boots.sort()
            ci = ([round(boots[int(0.025 * len(boots))], 4),
                   round(boots[int(0.975 * len(boots)) - 1], 4)]
                  if boots else None)

            blk["date_level"] = {
                "n_dates": len(dm),
                "n_single_admission_dates": singles,
                "mean_of_date_means_pct": round(st.mean(dm), 4),
                "n_weighted_date_mean_pct": round(wmean, 4),
                "median_of_date_means_pct": round(st.median(dm), 4),
                "note": ("mean_of_date_means equal-weights every date, so a "
                         "1-admission day counts as much as a 33-admission "
                         "day · n_weighted recovers the row-level mean"),
            }
            blk["uncertainty"] = {
                "method": "date-block bootstrap · whole dates resampled",
                "n_bootstrap": N_BOOTSTRAP,
                "ci95_row_mean_pct": ci,
                "ci_excludes_zero": bool(ci and (ci[0] > 0 or ci[1] < 0)),
                "note": ("rows inside a date are dependent · resampling rows "
                         "would understate the interval"),
            }
            blk["cost_sensitivity"] = {
                ("mean_net_at_%.2f_pct" % c): round(st.mean(got) - c, 4)
                for c in COST_GRID_PCT}
            blk["evidence_class"] = (
                "CONFIRMATORY-ELIGIBLE" if len(dm) >= MIN_DATES_CONFIRMATORY
                else "EXPLORATORY")
            blk["min_dates_required"] = MIN_DATES_CONFIRMATORY
        rep["horizons"][str(h)] = blk

    rep["data_quality"] = data_quality(root, market, adm, out)
    return rep


def data_quality(root: Path, market: str, adm: list, out: dict) -> dict:
    """Expose gaps rather than smoothing over them."""
    dates = sorted({a["as_of"] for a in adm})
    gaps = []
    for i in range(1, len(dates)):
        d0 = pd.Timestamp(dates[i - 1])
        d1 = pd.Timestamp(dates[i])
        bd = len(pd.bdate_range(d0, d1)) - 1
        if bd > 3:
            gaps.append({"from": dates[i - 1], "to": dates[i],
                         "business_days": bd})
    keys = list(out.keys())
    return {
        "admission_date_gaps_over_3_business_days": gaps,
        "n_outcome_keys": len(keys),
        "duplicate_outcome_keys": len(keys) - len(set(keys)),
        "unmatched_admissions_all_horizons": sum(
            1 for a in adm
            if all(out.get((a["as_of"], a["ticker"], h)) is None
                   for h in HORIZONS)),
    }


def write(root: Path, market: str, payload: dict) -> Path:
    p = (Path(root) / "reports" / "research" / "r3"
         / ("cohort_baseline_%s.json" % market))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p
