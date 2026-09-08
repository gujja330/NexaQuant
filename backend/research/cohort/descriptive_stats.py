"""DESCRIPTIVE STATISTICS ENGINE · NEXT 1 · CEO 2026-09-08.

> "For every important variable, calculate: count, missing %, mean, median,
>  std, variance, min/max, Q1/Q3, IQR, MAD, skewness, kurtosis, percentile
>  bands ... winner vs loser distributions, severe-loss vs normal
>  distributions. This becomes the descriptive baseline before ML is
>  trusted."

EVERY PROFILE CARRIES ITS TICKER CONCENTRATION
-----------------------------------------------
This is the one design decision that matters, and it is not optional.

Earlier today a cohort cell reported "61 observations, 0% winners" and was
presented as the clearest loss signature in the study. It was six tickers,
with ITC (29) and IRCTC (20) supplying 80% of it - two stocks falling in
August, sampled repeatedly through a 10-day forward window.

So no statistic here is emitted without `n_tickers`, `top_ticker_share_pct`
and `effective_units` beside it. A mean over 456 rows drawn from 37 names
is a mean over 37 names, and the reader is told so in the same breath.
`concentration_warning` fires when one ticker exceeds 25% of a cohort.

WINNER / LOSER / SEVERE-LOSS ARE PROFILED SEPARATELY
-----------------------------------------------------
Per the directive, each variable is profiled over the whole population and
over three sub-cohorts, so the question "what did winners look like versus
losers" is answered distributionally rather than by two means.

Severe loss = bottom decile of the horizon's cross-section, matching the
definition already used by the ML discovery layer so the two agree.

RESEARCH ONLY. Reads the cohort, writes one report, touches no engine.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.descriptive_stats.v1"
HORIZON = "fwd_10d_pct"
SEVERE_Q = 0.10
CONCENTRATION_WARN_PCT = 25.0
PERCENTILES = [1, 5, 10, 25, 50, 75, 90, 95, 99]

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


def _pct(s: list, p: float) -> float:
    """Linear-interpolated percentile · no numpy dependency needed."""
    if not s:
        return float("nan")
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def concentration(rows: list, horizon_days: int = 10) -> dict:
    """The guard rail · reported beside every statistic."""
    tick = Counter(str(r.get("ticker") or "") for r in rows)
    tick.pop("", None)
    n = len(rows) or 1
    top_n, top_c = (tick.most_common(1)[0] if tick else ("-", 0))
    from backend.research.ml_discovery.effective_sample import measure
    eff = measure(rows, horizon_days)["effective_units"] if rows else 0
    share = round(top_c / n * 100, 1)
    return {
        "n_rows": len(rows),
        "n_tickers": len(tick),
        "effective_units": eff,
        "top_ticker": top_n,
        "top_ticker_share_pct": share,
        "top3_share_pct": round(
            sum(c for _, c in tick.most_common(3)) / n * 100, 1),
        "rows_per_ticker": round(len(rows) / max(1, len(tick)), 2),
        "concentration_warning": bool(share > CONCENTRATION_WARN_PCT),
        "evidence_tier_on_effective_units": tier(eff),
    }


def numeric_profile(vals: list) -> dict:
    v = sorted(x for x in vals if x is not None)
    n = len(v)
    if n == 0:
        return {"count": 0}
    mean = sum(v) / n
    var = sum((x - mean) ** 2 for x in v) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    med = _pct(v, 50)
    mad = sorted(abs(x - med) for x in v)
    q1, q3 = _pct(v, 25), _pct(v, 75)
    iqr = q3 - q1
    skew = kurt = None
    if sd > 0 and n > 2:
        m3 = sum((x - mean) ** 3 for x in v) / n
        m4 = sum((x - mean) ** 4 for x in v) / n
        skew = round(m3 / sd ** 3, 4)
        kurt = round(m4 / sd ** 4 - 3.0, 4)     # excess kurtosis
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {
        "count": n,
        "mean": round(mean, 4), "median": round(med, 4),
        "std": round(sd, 4), "variance": round(var, 4),
        "min": round(v[0], 4), "max": round(v[-1], 4),
        "q1": round(q1, 4), "q3": round(q3, 4), "iqr": round(iqr, 4),
        "mad": round(_pct(mad, 50), 4),
        "skewness": skew, "excess_kurtosis": kurt,
        "coefficient_of_variation": (round(sd / abs(mean), 4)
                                     if mean else None),
        "percentiles": {f"p{p}": round(_pct(v, p), 4) for p in PERCENTILES},
        "outliers_low": sum(1 for x in v if x < lo),
        "outliers_high": sum(1 for x in v if x > hi),
        "outlier_pct": round(sum(1 for x in v if x < lo or x > hi) / n * 100, 2),
    }


def _wilson(k: int, n: int, z: float = 1.96) -> list:
    """Wilson interval · correct at the small n this cohort produces,
    where a normal approximation would run past 0 or 100."""
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, (c - m) / d) * 100, 2),
            round(min(1.0, (c + m) / d) * 100, 2)]


def categorical_profile(rows: list, key, horizon: str, severe_cut: float) -> dict:
    groups = {}
    for r in rows:
        k = key(r)
        if k is None:
            continue
        groups.setdefault(str(k), []).append(r)
    out = {}
    for k, g in sorted(groups.items()):
        rets = [_num(r.get(horizon)) for r in g]
        rets = [x for x in rets if x is not None]
        if not rets:
            continue
        wins = sum(1 for x in rets if x > 0)
        sev = sum(1 for x in rets if x <= severe_cut)
        conc = concentration(g)
        out[k] = {
            "n": len(rets),
            "share_of_population_pct": round(len(g) / max(1, len(rows)) * 100, 1),
            "win_rate_pct": round(wins / len(rets) * 100, 1),
            "win_rate_ci95": _wilson(wins, len(rets)),
            "severe_loss_rate_pct": round(sev / len(rets) * 100, 1),
            "severe_loss_ci95": _wilson(sev, len(rets)),
            "expectancy_pct": round(sum(rets) / len(rets), 3),
            "median_pct": round(_pct(sorted(rets), 50), 3),
            "concentration": conc,
            "evidence_tier": tier(conc["effective_units"]),
        }
    return out


NUMERIC_VARS = [
    "confidence_pct", "rank", "ma20_dist_pct", "ma50_dist_pct",
    "ma200_dist_pct", "momentum_20d_pct", "momentum_60d_pct",
    "vol_20d_pct", "avg_dv_60d", "rsi_14", "entry_price_at_pred",
    "stop_at_pred", "mae_pct", "mfe_pct",
    "fund_roe", "fund_pe", "fund_pb", "fund_debt_equity",
    "fund_quality_score",
]

CATEGORICAL_VARS = [
    ("investability_band", lambda r: (str(r.get("investability_band") or "")
                                      .upper() or None)),
    ("liquidity_bucket_60d", lambda r: r.get("_liquidity_bucket")),
    ("trend_above_ma200", lambda r: (
        None if _num(r.get("ma200_dist_pct")) is None
        else ("ABOVE" if _num(r.get("ma200_dist_pct")) > 0 else "BELOW"))),
    ("sector_EXPLORATORY_NOT_PIT", lambda r: (
        str(r.get("sector")) if r.get("sector")
        and str(r.get("sector")).upper() not in
        ("NONE", "UNKNOWN", "", "?", "LARGE-CAP") else None)),
]


def analyse(root: Path, market: str) -> dict:
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery import temporal

    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}
    temporal.attach(root, market, rows)

    pop = [r for r in rows if _num(r.get(HORIZON)) is not None]
    rets = sorted(_num(r.get(HORIZON)) for r in pop)
    severe_cut = _pct(rets, SEVERE_Q * 100) if rets else 0.0

    cohorts = {
        "ALL": pop,
        "WINNERS": [r for r in pop if _num(r.get(HORIZON)) > 0],
        "LOSERS": [r for r in pop if _num(r.get(HORIZON)) <= 0],
        "SEVERE_LOSS": [r for r in pop if _num(r.get(HORIZON)) <= severe_cut],
    }

    # Temporal features join the numeric set automatically.
    temporal_vars = sorted({k for r in pop for k in r
                            if k.startswith(("ret_lag_", "roll_", "dist_ma_",
                                             "vol_expansion", "ma20_dist_slope",
                                             "momentum_persistence"))
                            or "_lag_" in k or k.endswith("_change")})
    numeric = NUMERIC_VARS + [v for v in temporal_vars
                              if v not in NUMERIC_VARS]

    profiles = {}
    for var in numeric:
        entry = {"variable": var,
                 "missing_pct_population": round(
                     sum(1 for r in pop if _num(r.get(var)) is None)
                     / max(1, len(pop)) * 100, 1)}
        for cname, crows in cohorts.items():
            entry[cname] = numeric_profile([_num(r.get(var)) for r in crows])
        w, l = entry["WINNERS"], entry["LOSERS"]
        if w.get("count") and l.get("count") and w.get("std") is not None:
            pooled = math.sqrt(((w["std"] ** 2) + (l["std"] ** 2)) / 2) or None
            entry["winner_minus_loser_mean"] = round(w["mean"] - l["mean"], 4)
            entry["cohens_d"] = (round((w["mean"] - l["mean"]) / pooled, 4)
                                 if pooled else None)
        profiles[var] = entry

    cats = {name: categorical_profile(pop, fn, HORIZON, severe_cut)
            for name, fn in CATEGORICAL_VARS}

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DESCRIPTIVE BASELINE · research only · no production rule",
        "market": market.lower(),
        "horizon": HORIZON,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "severe_loss_cut_pct": round(severe_cut, 3),
        "cohort_concentration": {k: concentration(v) for k, v in cohorts.items()},
        "n_numeric_variables": len(numeric),
        "n_categorical_variables": len(cats),
        "numeric": profiles,
        "categorical": cats,
        "reading_note": (
            "Every count is accompanied by n_tickers and effective_units. A "
            "mean over 456 rows drawn from 37 names is a mean over 37 names. "
            "concentration_warning fires above %.0f%% single-ticker share."
            % CONCENTRATION_WARN_PCT),
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "cohort"
            / f"descriptive_stats_{market.lower()}.json")


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
    ap = argparse.ArgumentParser(description="Descriptive statistics engine")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = analyse(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        p = emit(root, rep)
        c = rep["cohort_concentration"]["ALL"]
        print(f"descriptive:{m} · {rep['n_numeric_variables']} numeric · "
              f"{rep['n_categorical_variables']} categorical · rows "
              f"{c['n_rows']} · tickers {c['n_tickers']} · effective "
              f"{c['effective_units']} · tier "
              f"{c['evidence_tier_on_effective_units']}")
        print(f"    -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
