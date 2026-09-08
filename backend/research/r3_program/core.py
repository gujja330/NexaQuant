"""R3 PROGRAMME CORE · shared evaluation primitives.

Every R3 module in this package shares these primitives so that a result
cannot become favourable merely by being measured differently in one place.

THE ONE RULE THAT GOVERNS THIS FILE
------------------------------------
Rows are not evidence. A cohort of 725 India rows holds 45 names over 26
dates; rows of one name on adjacent days are near-copies. Every resampling
routine here therefore resamples TICKERS, and every split here is
ticker-disjoint or ticker x date disjoint. This was learned the hard way:
Wave 2C produced p = 0.000 at row level and p = 0.386 on the units that
actually vary.

ECONOMIC VALUE IS NOT AUC
-------------------------
`decision_value` scores a TAKE/AVOID/ABSTAIN policy against the baseline
of taking every R2 candidate, net of a cost assumption. A model that ranks
well but changes no decision has no value here, which is the intended
behaviour.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Callable, Optional

FORWARD_HORIZON = 10
EMBARGO_DAYS = 5
DEFAULT_COST_PCT = 0.25          # round-trip cost + slippage assumption
SEVERE_Q = 0.10

# Evidence tiers · existing AEGIS taxonomy · NOT automatic pass conditions
EVIDENCE_TIERS = ((5, "OBSERVATION"), (15, "HYPOTHESIS"), (30, "RESEARCH_SIGNAL"),
                  (50, "STRONGER_EVIDENCE"), (10 ** 9, "VALIDATION_CANDIDATE"))

DISPOSITIONS = ("VALIDATED", "CONDITIONAL", "RESEARCH_ONLY", "DESCRIPTIVE_ONLY",
                "REJECTED", "INVALIDATED", "BLOCKED", "INSUFFICIENT_SUBSTRATE")


def evidence_tier(n_units: int) -> str:
    """Tier by EFFECTIVE units, never by row count."""
    for lim, name in EVIDENCE_TIERS:
        if n_units < lim:
            return name
    return "VALIDATION_CANDIDATE"


def num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def to_date(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def auc(y: list, p: list) -> Optional[float]:
    pos = [i for i, v in enumerate(y) if v == 1]
    neg = [i for i, v in enumerate(y) if v == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(p)), key=lambda i: p[i])
    rank = [0.0] * len(p)
    for r, i in enumerate(order, 1):
        rank[i] = r
    return round((sum(rank[i] for i in pos) - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)), 4)


def pr_auc(y: list, p: list) -> Optional[float]:
    """Average precision · the honest metric when events are ~10%."""
    if not any(y):
        return None
    order = sorted(range(len(p)), key=lambda i: -p[i])
    tp, tot, s = 0, sum(y), 0.0
    for k, i in enumerate(order, 1):
        if y[i] == 1:
            tp += 1
            s += tp / k
    return round(s / tot, 4)


def brier(y: list, p: list) -> Optional[float]:
    if not y:
        return None
    return round(sum((a - b) ** 2 for a, b in zip(y, p)) / len(y), 4)


def ece(y: list, p: list, bins: int = 10) -> Optional[float]:
    """Expected calibration error · does 0.7 actually mean 70%."""
    if len(y) < 20:
        return None
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, v in enumerate(p)
               if (lo <= v < hi or (b == bins - 1 and v == 1.0))]
        if not idx:
            continue
        conf = sum(p[i] for i in idx) / len(idx)
        acc = sum(y[i] for i in idx) / len(idx)
        tot += len(idx) / len(y) * abs(conf - acc)
    return round(tot, 4)


def calibration_line(y: list, p: list) -> dict:
    """Slope/intercept of observed-on-predicted · 1.0 / 0.0 is perfect."""
    n = len(y)
    if n < 20:
        return {}
    mp, my = sum(p) / n, sum(y) / n
    sxx = sum((v - mp) ** 2 for v in p)
    if sxx == 0:
        return {}
    slope = sum((a - mp) * (b - my) for a, b in zip(p, y)) / sxx
    return {"slope": round(slope, 4), "intercept": round(my - slope * mp, 4)}


def ticker_bootstrap_ci(rows: list, stat: Callable, n_boot: int = 400,
                        seed: int = 20260908) -> Optional[dict]:
    """95% CI resampling NAMES, because names are the independent units."""
    import numpy as np
    by = {}
    for i, r in enumerate(rows):
        by.setdefault(r["ticker"], []).append(i)
    names = list(by)
    if len(names) < 8:
        return None
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(len(names), size=len(names), replace=True)
        sel = [i for k in pick for i in by[names[k]]]
        v = stat(sel)
        if v is not None:
            vals.append(v)
    if len(vals) < 100:
        return None
    vals.sort()
    lo, hi = vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]
    return {"lo": round(lo, 4), "hi": round(hi, 4),
            "excludes_zero": bool(lo > 0 or hi < 0), "n_boot": len(vals)}


def ticker_folds(rows: list, k: int = 5) -> list:
    """Ticker-disjoint fold assignment · a name never trains on itself."""
    names = sorted({r["ticker"] for r in rows})
    fold = {t: i % k for i, t in enumerate(names)}
    return [fold[r["ticker"]] for r in rows]


def effective_units(rows: list, horizon: int = FORWARD_HORIZON) -> int:
    """Sum over names of floor(span / horizon) · FLOOR, never ceil.

    A name observed over 26 days contributes 2 independent 10-day outcomes,
    not 26. Using ceil here once scored India at 70 units against a 50-unit
    gate it should have failed.
    """
    by = {}
    for r in rows:
        d = to_date(r.get("date") or r.get("prediction_date"))
        if d:
            by.setdefault(r["ticker"], []).append(d)
    tot = 0
    for ds in by.values():
        tot += max(1, (max(ds) - min(ds)).days // horizon)
    return tot


def effective_date_units(rows: list, horizon: int = FORWARD_HORIZON) -> int:
    """Independent TIME points · floor(span_of_cohort / horizon).

    The ticker count and the date count constrain different claims, and
    conflating them is how a thin cohort looks rich. USA carries 495 names
    but only 7 dates inside a 28-day window: every one of those names moved
    together with the market on those seven mornings. For any claim about
    time - drift, regime, "does it still work next month" - the units are
    the dates, and there are barely a handful.
    """
    ds = [d for d in (to_date(r.get("date") or r.get("prediction_date"))
                      for r in rows) if d]
    if not ds:
        return 0
    return max(1, (max(ds) - min(ds)).days // horizon)


def substrate_assessment(rows: list, horizon: int = FORWARD_HORIZON) -> dict:
    """Both unit counts, plus the tier each supports · never just the big one."""
    tu = effective_units(rows, horizon)
    du = effective_date_units(rows, horizon)
    return {
        "n_rows": len(rows),
        "n_tickers": len({r["ticker"] for r in rows}),
        "n_dates": len({str(r.get("date") or r.get("prediction_date"))[:10]
                        for r in rows}),
        "effective_ticker_units": tu,
        "effective_date_units": du,
        "tier_cross_sectional": evidence_tier(tu),
        "tier_temporal": evidence_tier(du),
        "binding_constraint": ("dates" if du < tu else "tickers"),
        "note": ("cross-sectional claims are limited by names (%d units), "
                 "temporal claims by dates (%d units) · quote the one that "
                 "matches the claim" % (tu, du)),
    }


def date_concentration(rows: list) -> dict:
    """How much of this cohort is really ONE market episode.

    USA carries 1,040 rows across seven dates, but 2026-08-11 and
    2026-08-12 supply 972 of them - two consecutive mornings whose 10-day
    forward windows overlap by nine days. Ticker-disjoint folds are blind
    to this: every fold contains the same two dates and the same market
    move, so a model can score well out-of-sample on NAMES while having
    seen exactly one realisation of the market.

    A result measured on one episode is a description of that episode.
    """
    from collections import Counter
    c = Counter(str(r.get("date") or r.get("prediction_date"))[:10] for r in rows)
    tot = sum(c.values())
    top = c.most_common()
    top1 = top[0][1] / tot * 100 if top else 0.0
    top2 = sum(n for _, n in top[:2]) / tot * 100 if top else 0.0
    return {
        "n_dates": len(c),
        "rows_by_date": dict(top),
        "top_date_share_pct": round(top1, 1),
        "top_2_dates_share_pct": round(top2, 1),
        "single_episode": bool(top2 >= 80.0),
        "n_dates_with_ge_5pct": sum(1 for _, n in top if n / tot >= 0.05),
        "rule": ("a cohort where two dates carry 80% or more of the rows is "
                 "ONE episode · no out-of-sample claim about time can rest "
                 "on it, however many names it holds"),
    }


def sector_validity(rows: list) -> dict:
    """Is the sector column a sector, or a placeholder wearing the name.

    USA reports 'Large-Cap' on 972 of 1,040 rows. That is a capitalisation
    bucket, not a sector, and any sector-conditioned finding built on it
    would be a finding about nothing.
    """
    from collections import Counter
    c = Counter(str(r.get("sector")) for r in rows if r.get("sector"))
    tot = sum(c.values())
    labels = [k for k in c if k not in ("None", "-", "—", "")]
    dom = (c.most_common(1)[0] if c else (None, 0))
    share = round(dom[1] / tot * 100, 1) if tot else 0.0
    usable = len(labels) >= 4 and share < 70.0
    return {"n_distinct_labels": len(labels), "labels": sorted(labels)[:12],
            "dominant_label": dom[0], "dominant_share_pct": share,
            "usable_as_sector": usable,
            "reason": ("usable" if usable else
                       "only %d distinct labels and '%s' covers %.1f%% · this "
                       "is not sector information" % (len(labels), dom[0], share))}


def decision_value(rows: list, action: Callable,
                   cost_pct: float = DEFAULT_COST_PCT,
                   fwd_key: str = "fwd") -> dict:
    """Score a TAKE/AVOID/ABSTAIN policy against 'take every R2 candidate'.

    This is the gate the mandate calls final. A model may rank beautifully
    and still land here with nothing: if it AVOIDs rows whose mean outcome
    matches what it takes, the decision did not change and the value is
    zero regardless of AUC.
    """
    base = [v for v in (num(r.get(fwd_key)) for r in rows) if v is not None]
    if not base:
        return {}
    taken, avoided, abstained = [], [], []
    for r in rows:
        v = num(r.get(fwd_key))
        if v is None:
            continue
        a = action(r)
        (taken if a == "TAKE" else avoided if a == "AVOID"
         else abstained).append(v)
    n_b, n_t = len(base), len(taken)
    sev = sorted(base)[max(0, int(len(base) * SEVERE_Q) - 1)]
    out = {
        "n_candidates": n_b,
        "baseline_take_all": {
            "n": n_b, "mean_pct": round(sum(base) / n_b - cost_pct, 4),
            "win_rate_pct": round(sum(1 for v in base if v > 0) / n_b * 100, 1),
            "severe_rate_pct": round(sum(1 for v in base if v <= sev)
                                     / n_b * 100, 1)},
        "n_take": n_t, "n_avoid": len(avoided), "n_abstain": len(abstained),
        "take_rate_pct": round(n_t / n_b * 100, 1),
        "cost_assumption_pct": cost_pct,
    }
    if n_t:
        out["policy"] = {
            "n": n_t, "mean_pct": round(sum(taken) / n_t - cost_pct, 4),
            "win_rate_pct": round(sum(1 for v in taken if v > 0) / n_t * 100, 1),
            "severe_rate_pct": round(sum(1 for v in taken if v <= sev)
                                     / n_t * 100, 1)}
        out["delta_mean_pp"] = round(out["policy"]["mean_pct"]
                                     - out["baseline_take_all"]["mean_pct"], 4)
        out["delta_severe_pp"] = round(out["policy"]["severe_rate_pct"]
                                       - out["baseline_take_all"]["severe_rate_pct"], 2)
        out["opportunity_forgone_pct"] = round(100 - out["take_rate_pct"], 1)
    if avoided:
        out["avoided_mean_pct"] = round(sum(avoided) / len(avoided), 4)
    return out


def load_pop(root, market: str, fwd_key: str = "fwd_10d_pct",
             features: Optional[list] = None) -> list:
    """Canonical population loader · one row per (ticker, date) with outcome."""
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    rows = load_cohort(root, market)
    seen, out = set(), []
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        d = str(r.get("prediction_date") or "")[:10]
        f = num(r.get(fwd_key))
        if not t or not d or f is None or (t, d) in seen:
            continue
        seen.add((t, d))
        e = {"ticker": t, "date": d, "fwd": f, "raw": r}
        for k in (features or []):
            e[k] = num(r.get(k))
        e["sector"] = r.get("sector")
        out.append(e)
    out.sort(key=lambda x: (x["date"], x["ticker"]))
    return out


def severe_cut(rows: list, q: float = SEVERE_Q) -> float:
    f = sorted(r["fwd"] for r in rows)
    return f[max(0, int(len(f) * q) - 1)]
