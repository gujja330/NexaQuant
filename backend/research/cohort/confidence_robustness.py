"""R3-B · CONFIDENCE ROBUSTNESS · CEO 2026-09-08.

> "If confidence remains anti-predictive WITHIN names, that becomes a much
>  stronger structural finding. If it disappears, we record it as a
>  cross-sectional concentration artifact."

WHY THIS IS THE RIGHT NEXT TEST
--------------------------------
Confidence gates production entry at a 0.55 floor, and every measurement
so far says it does not separate outcomes:

    India   losers 51.3  winners 47.5   p=0.27   (losers HIGHER)
    USA     losers 79.5  winners 77.8   p=0.57   (losers HIGHER)
    USA     >=90 bucket n=299 -> +0.067%  vs  <55 bucket n=99 -> +0.487%

But every one of those is a POOLED, cross-sectional comparison, and this
cohort is concentrated: 456 India rows from 37 tickers. A pooled effect
can be produced entirely by ticker mix - if the names that happen to carry
high confidence also happen to be the names that fell in August, pooled
confidence looks anti-predictive while telling us nothing about whether
confidence is informative FOR A GIVEN NAME.

Simpson's paradox is the specific risk, and it is cheap to test.

WHAT IS COMPUTED
----------------
  pooled              the naive effect · what has been reported so far
  within_ticker       each ticker centred on its own mean · the effect
                      that survives after every name is its own control
  ticker_weighted     each ticker contributes equally, not proportionally
                      to how often it was sampled
  leave_one_out       drop each ticker in turn · is the sign stable, or is
                      one name carrying the whole result
  confidence_x_trend  does confidence become informative conditional on
                      trajectory

The verdict distinguishes three outcomes explicitly:
  STRUCTURAL          effect holds within names -> a real finding about
                      the confidence score
  CONCENTRATION_ARTEFACT   pooled effect vanishes within names -> the
                      earlier reports were a ticker-mix artefact
  INCONCLUSIVE        too few names or too little within-ticker variance

RESEARCH ONLY.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.confidence_robustness.v1"
HORIZON = "fwd_10d_pct"
MIN_OBS_PER_TICKER = 5


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _pearson(xs, ys) -> Optional[float]:
    n = len(xs)
    if n < 5:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 4)


def _spearman(xs, ys) -> Optional[float]:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    return _pearson(rank(xs), rank(ys))


def analyse(root: Path, market: str) -> dict:
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery import temporal

    rows = load_cohort(root, market)
    temporal.attach(root, market, rows)
    pop = [r for r in rows
           if _num(r.get("confidence_pct")) is not None
           and _num(r.get(HORIZON)) is not None]
    if len(pop) < 60:
        return {"market": market, "error": "n=%d" % len(pop)}

    conf = [_num(r["confidence_pct"]) for r in pop]
    ret = [_num(r[HORIZON]) for r in pop]

    pooled = {
        "n": len(pop),
        "pearson": _pearson(conf, ret),
        "spearman": _spearman(conf, ret),
        "mean_conf_winners": round(
            sum(c for c, v in zip(conf, ret) if v > 0)
            / max(1, sum(1 for v in ret if v > 0)), 3),
        "mean_conf_losers": round(
            sum(c for c, v in zip(conf, ret) if v <= 0)
            / max(1, sum(1 for v in ret if v <= 0)), 3),
    }

    # ── within-ticker · every name is its own control ───────────────────
    by = defaultdict(list)
    for r, c, v in zip(pop, conf, ret):
        by[str(r.get("ticker"))].append((c, v))
    usable = {t: g for t, g in by.items() if len(g) >= MIN_OBS_PER_TICKER}
    dc, dv, per_ticker = [], [], {}
    for t, g in usable.items():
        cs = [c for c, _ in g]
        vs = [v for _, v in g]
        if len(set(cs)) < 2:
            continue                       # no within-name variance to use
        mc, mv = sum(cs) / len(cs), sum(vs) / len(vs)
        dc += [c - mc for c in cs]
        dv += [v - mv for v in vs]
        per_ticker[t] = {"n": len(g), "pearson": _pearson(cs, vs),
                         "conf_range": round(max(cs) - min(cs), 2)}
    within = {
        "n_tickers_usable": len(per_ticker),
        "n_obs": len(dc),
        "pearson_demeaned": _pearson(dc, dv) if dc else None,
        "spearman_demeaned": _spearman(dc, dv) if dc else None,
        "per_ticker": dict(sorted(per_ticker.items())),
    }
    pt = [v["pearson"] for v in per_ticker.values() if v["pearson"] is not None]
    within["mean_of_per_ticker_pearson"] = (
        round(sum(pt) / len(pt), 4) if pt else None)
    within["share_negative_pct"] = (
        round(sum(1 for x in pt if x < 0) / len(pt) * 100, 1) if pt else None)

    # ── ticker-weighted · each name counts once ─────────────────────────
    tw = None
    if pt:
        tw = {"n_tickers": len(pt),
              "mean_pearson": round(sum(pt) / len(pt), 4),
              "median_pearson": round(sorted(pt)[len(pt) // 2], 4)}

    # ── leave-one-ticker-out on the POOLED effect ───────────────────────
    loo = []
    base_p = pooled["pearson"]
    for t in sorted(by):
        keep = [(c, v) for tt, g in by.items() if tt != t for c, v in g]
        if len(keep) < 30:
            continue
        r = _pearson([c for c, _ in keep], [v for _, v in keep])
        if r is not None:
            loo.append({"dropped": t, "pearson": r,
                        "delta": round(r - (base_p or 0), 4)})
    loo.sort(key=lambda d: -abs(d["delta"]))
    signs = {(1 if d["pearson"] > 0 else -1) for d in loo}
    loo_stable = len(signs) <= 1

    # ── confidence x trajectory ─────────────────────────────────────────
    inter = {}
    slope = [_num(r.get("ma20_dist_slope_10d")) for r in pop]
    have = [i for i, s in enumerate(slope) if s is not None]
    if len(have) >= 60:
        med = sorted(slope[i] for i in have)[len(have) // 2]
        for lbl, sel in (("slope_below_median", lambda s: s <= med),
                         ("slope_above_median", lambda s: s > med)):
            idx = [i for i in have if sel(slope[i])]
            if len(idx) >= 30:
                inter[lbl] = {
                    "n": len(idx),
                    "pearson": _pearson([conf[i] for i in idx],
                                        [ret[i] for i in idx]),
                    "mean_return_pct": round(
                        sum(ret[i] for i in idx) / len(idx), 3)}

    wp = within["pearson_demeaned"]
    if within["n_tickers_usable"] < 8 or wp is None:
        verdict = "INCONCLUSIVE · too few names with within-ticker variance"
    elif base_p is not None and abs(wp) < abs(base_p) * 0.5:
        verdict = ("CONCENTRATION_ARTEFACT · the pooled effect (%.4f) largely "
                   "vanishes within names (%.4f) · earlier confidence "
                   "reports were driven by ticker mix" % (base_p, wp))
    elif wp < -0.05:
        verdict = ("STRUCTURAL · confidence remains ANTI-predictive within "
                   "names (demeaned r=%.4f) · a real property of the score" % wp)
    elif wp > 0.05:
        verdict = ("STRUCTURAL · confidence is POSITIVELY predictive within "
                   "names (demeaned r=%.4f) · the pooled view was misleading" % wp)
    else:
        verdict = ("NO WITHIN-NAME EFFECT · demeaned r=%.4f · confidence "
                   "carries no information for a given name" % wp)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "RESEARCH ONLY · no production rule · 0.55 floor unchanged",
        "market": market.lower(),
        "horizon": HORIZON,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pooled": pooled,
        "within_ticker": within,
        "ticker_weighted": tw,
        "leave_one_ticker_out": {"stable_sign": loo_stable,
                                 "n_evaluated": len(loo),
                                 "largest_swings": loo[:5]},
        "confidence_x_trajectory": inter,
        "verdict": verdict,
    }


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "cohort"
         / f"confidence_robustness_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "cohort"
         / f"confidence_robustness_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3-B confidence robustness")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = analyse(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        emit(root, rep)
        p, w = rep["pooled"], rep["within_ticker"]
        print(f"confidence:{m} · pooled r={p['pearson']} · within-name "
              f"r={w['pearson_demeaned']} ({w['n_tickers_usable']} names, "
              f"{w['n_obs']} obs)")
        print(f"    {rep['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
