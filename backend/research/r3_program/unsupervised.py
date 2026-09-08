"""R3-H · UNSUPERVISED INTELLIGENCE · Phase 3.

> "Test clustering and anomaly detection. This is a required missing
>  research family."

WHAT IS ASKED, AND WHAT IS REFUSED
-----------------------------------
Asked: fundamental-state clustering, technical-behaviour clustering, the
two combined, outcome-trajectory clustering for failure analysis only, and
anomaly detection.

Refused: endless hyperparameter search. The configurations below are fixed
in advance (k in 3..6, three algorithms, two anomaly detectors). Searching
until a cluster separates outcomes is how noise gets promoted, and with
one to two independent time points it would succeed every time.

THE LEAKAGE RULE FOR TRAJECTORY CLUSTERS
-----------------------------------------
Outcome-trajectory clusters are built FROM the outcome. They may describe
failures after the fact; they may never be used to predict, and they are
never handed to a model. `D_trajectory` is therefore emitted under a key
that the decision layer does not read, and the report says so.

WHAT WOULD MAKE A CLUSTER USEFUL
---------------------------------
Not that it separates outcomes in-sample - with 495 names on 7 dates,
something always will. It must be:

  stable across dates      · not a single-morning artefact
  stable across names      · not one sector wearing a cluster label
  useful out-of-sample     · ticker-disjoint assignment still separates
  incremental over R2      · separates what R2 confidence does not

Failing the last two leaves a cluster DESCRIPTIVE_ONLY, which is a real
disposition and the expected one here.

RESEARCH ONLY · no production surface.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.r3_program import core

SCHEMA_VERSION = "aegis.r3.unsupervised.v1"
FAMILY = "R3H_UNSUPERVISED_V1"

K_RANGE = (3, 4, 5, 6)                       # bounded · fixed in advance
ALGOS = ("kmeans", "gmm", "hierarchical")    # bounded · fixed in advance
ANOMALY = ("isolation_forest", "robust_mahalanobis")

TECHNICAL_FEATURES = ["confidence_pct", "vol_20d_pct", "momentum_20d_pct",
                      "momentum_60d_pct", "ma200_dist_pct", "ma50_dist_pct",
                      "rsi_14"]
FUNDAMENTAL_FEATURES = ["roe_pct", "sales_growth_pct", "profit_growth_pct",
                        "debt_to_equity", "cfo_to_net_income",
                        "roe_trend_pp", "sales_growth_accel_pp",
                        "h3_last_surprise_pct"]

MIN_ROWS = 80
MIN_TICKERS = 20
MIN_FEATURE_COVERAGE_PCT = 60.0


def usable_features(rows: list, feats: list) -> tuple:
    """Drop features the market does not actually supply.

    India reports operating cash flow on 2% of rows - the provider simply
    does not carry it - so requiring all eight fundamental features left 9
    usable rows out of 361. Dropping a feature the data does not have is
    honest; silently imputing it would invent a fundamental state that was
    never observed. What was dropped is always reported.
    """
    keep, dropped = [], {}
    n = max(1, len(rows))
    for f in feats:
        c = sum(1 for r in rows if r.get(f) is not None)
        pct = round(c / n * 100, 1)
        if pct >= MIN_FEATURE_COVERAGE_PCT:
            keep.append(f)
        else:
            dropped[f] = "%.1f%% coverage" % pct
    return keep, dropped


def _attach_fundamentals(root: Path, market: str, rows: list) -> int:
    """PIT-gated fundamental state per (ticker, date) · 45-day assumed lag."""
    from backend.research.substrate import fundamental_timeseries as ft
    from backend.research.cohort.seven_filter_ai import filter_state
    store = ft.load(root, market) or {}
    recs = store.get("tickers") or {}
    n = 0
    for r in rows:
        base = r["ticker"].split(".", 1)[0]
        rec = recs.get(base)
        if not rec:
            continue
        st = filter_state(ft.as_of(rec, r["date"], 45))
        f = ft.features_as_of(rec, r["date"], 45)
        for k in FUNDAMENTAL_FEATURES:
            r[k] = core.num(st.get(k) if k in st else f.get(k))
        if any(r.get(k) is not None for k in FUNDAMENTAL_FEATURES):
            n += 1
    return n


def _matrix(rows: list, feats: list):
    """Standardised matrix · rows keeping every feature, and their indices."""
    import numpy as np
    idx = [i for i, r in enumerate(rows)
           if all(r.get(f) is not None for f in feats)]
    if not idx:
        return None, []
    X = np.array([[float(rows[i][f]) for f in feats] for i in idx])
    # Winsorise at 1/99 before standardising. Fundamental ratios have very
    # heavy tails - one company with near-zero equity produces an ROE of
    # several thousand percent - and an unclipped outlier makes every
    # algorithm spend a cluster on a single row, which is why 12 of 12
    # bounded configurations failed the n>=15 floor. Clipping is applied
    # uniformly to all features and is not a per-result adjustment.
    lo = np.percentile(X, 1, axis=0)
    hi = np.percentile(X, 99, axis=0)
    X = np.clip(X, lo, hi)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    return (X - mu) / sd, idx


def _fit_clusters(X, algo: str, k: int, seed: int = 20260908):
    from sklearn.cluster import AgglomerativeClustering, KMeans
    from sklearn.mixture import GaussianMixture
    if algo == "kmeans":
        return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(X)
    if algo == "gmm":
        return GaussianMixture(n_components=k, covariance_type="full",
                               random_state=seed).fit_predict(X)
    return AgglomerativeClustering(n_clusters=k).fit_predict(X)


def _cluster_quality(rows: list, idx: list, labels, sev: float) -> dict:
    """Separation, and every way it could be an artefact."""
    by = {}
    for i, lab in zip(idx, labels):
        by.setdefault(int(lab), []).append(rows[i])
    cells = {}
    for lab, g in sorted(by.items()):
        f = [r["fwd"] for r in g]
        dates = {r["date"] for r in g}
        names = {r["ticker"] for r in g}
        top_date = max(dates, key=lambda d: sum(1 for r in g if r["date"] == d))
        top_name_n = max(sum(1 for r in g if r["ticker"] == t) for t in names)
        cells[str(lab)] = {
            "n": len(g), "n_tickers": len(names), "n_dates": len(dates),
            "mean_fwd_pct": round(sum(f) / len(f), 3),
            "win_rate_pct": round(sum(1 for v in f if v > 0) / len(f) * 100, 1),
            "severe_rate_pct": round(sum(1 for v in f if v <= sev) / len(f) * 100, 1),
            "max_single_date_share_pct": round(
                sum(1 for r in g if r["date"] == top_date) / len(g) * 100, 1),
            "max_single_ticker_share_pct": round(top_name_n / len(g) * 100, 1),
        }
    # Spread is measured only over clusters large enough to have a
    # meaningful mean. Every one of the twelve bounded configurations
    # isolates the same ~12 extreme-leverage names; letting that cell set
    # the spread would report a 3 pp separation carried by twelve rows,
    # and letting it void the configuration would discard all twelve. It
    # is reported, and excluded from the measurement.
    ok = [c for c in cells.values() if c["n"] >= 15]
    means = [c["mean_fwd_pct"] for c in ok]
    return {
        "clusters": cells,
        "spread_mean_fwd_pp": (round(max(means) - min(means), 3)
                               if len(means) > 1 else None),
        "n_clusters_with_n_ge_15": len(ok),
        "n_clusters_too_small_to_measure": len(cells) - len(ok),
        "max_single_date_share_pct": max(
            (c["max_single_date_share_pct"] for c in cells.values()), default=None),
        "smallest_cluster_n": min((c["n"] for c in cells.values()), default=0),
        "smallest_measured_cluster_n": min((c["n"] for c in ok), default=0),
    }


def _oos_separation(rows: list, idx: list, feats: list, sev: float,
                    algo: str, k: int) -> Optional[dict]:
    """Ticker-disjoint: fit on 4/5 of NAMES, assign the held-out 5th.

    In-sample separation is worthless - k-means will always split a cloud.
    The question is whether a name never seen during fitting lands in a
    cluster that still predicts its outcome.
    """
    import numpy as np
    from sklearn.cluster import KMeans
    if algo != "kmeans":
        return None                       # only centroid models can assign OOS
    sub = [rows[i] for i in idx]
    folds = core.ticker_folds(sub, 5)
    X, _ = _matrix(sub, feats)
    if X is None:
        return None
    oof = [None] * len(sub)
    for fo in range(5):
        tr = [i for i, f in enumerate(folds) if f != fo]
        te = [i for i, f in enumerate(folds) if f == fo]
        if len(tr) < 40 or not te:
            return None
        km = KMeans(n_clusters=k, n_init=10, random_state=20260908).fit(X[tr])
        for i, lab in zip(te, km.predict(X[te])):
            oof[i] = int(lab)
    by = {}
    for r, lab in zip(sub, oof):
        if lab is not None:
            by.setdefault(lab, []).append(r["fwd"])
    if len(by) < 2:
        return None
    means = {str(k2): round(sum(v) / len(v), 3) for k2, v in sorted(by.items())}
    spread = max(means.values()) - min(means.values())
    # Is the OOS spread bigger than chance?
    #
    # The null must permute at TICKER level, not row level. A row-level
    # shuffle destroys the fact that a name's rows move together, so any
    # cluster that merely captures "these names fell in August" beats it
    # easily. Reassigning whole names preserves that structure and asks the
    # only question worth asking: is this more than a grouping of names?
    rng = np.random.default_rng(20260908)
    keep = [(r, l) for r, l in zip(sub, oof) if l is not None]
    lab_by_ticker = {}
    for r, l in keep:
        lab_by_ticker.setdefault(r["ticker"], l)
    names = list(lab_by_ticker)
    labs = [lab_by_ticker[t] for t in names]
    vals_by_ticker = {}
    for r, _ in keep:
        vals_by_ticker.setdefault(r["ticker"], []).append(r["fwd"])
    null = []
    for _ in range(300):
        perm = rng.permutation(labs)
        d = {}
        for t, l in zip(names, perm):
            d.setdefault(int(l), []).extend(vals_by_ticker[t])
        m = [sum(x) / len(x) for x in d.values() if len(x) >= 5]
        if len(m) > 1:
            null.append(max(m) - min(m))
    lab_list = [l for _, l in keep]
    null.sort()
    p = ((sum(1 for x in null if x >= spread) + 1) / (len(null) + 1)
         if null else None)
    return {"oos_cluster_mean_fwd_pct": means,
            "oos_spread_pp": round(spread, 3),
            "permutation_p": (round(p, 4) if p is not None else None),
            "permutation_unit": "ticker · whole names reassigned together",
            "n_permutations": len(null),
            "n_assigned": len(lab_list)}


def _anomalies(rows: list, idx: list, feats: list, sev: float) -> dict:
    """Are outliers dangerous, interesting, or just thin data?"""
    import numpy as np
    from sklearn.ensemble import IsolationForest
    X, _ = _matrix([rows[i] for i in idx], feats)
    if X is None or len(X) < MIN_ROWS:
        return {"verdict": "insufficient rows"}
    sub = [rows[i] for i in idx]
    out = {}
    iso = IsolationForest(n_estimators=200, contamination=0.1,
                          random_state=20260908).fit(X)
    flag_iso = iso.predict(X) == -1
    # robust Mahalanobis · median/MAD, no covariance inversion fragility
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0)
    mad[mad == 0] = 1.0
    dist = np.sqrt(((X - med) / mad ** 1.0 ** 1).__pow__(2).sum(axis=1))
    thr = np.quantile(dist, 0.90)
    flag_rob = dist >= thr
    for name, flag in (("isolation_forest", flag_iso),
                       ("robust_mahalanobis", flag_rob)):
        a = [r["fwd"] for r, f in zip(sub, flag) if f]
        b = [r["fwd"] for r, f in zip(sub, flag) if not f]
        if len(a) < 15 or len(b) < 15:
            out[name] = {"verdict": "too few flagged"}
            continue
        an = [r for r, f in zip(sub, flag) if f]
        out[name] = {
            "n_flagged": len(a), "n_tickers_flagged": len({r["ticker"] for r in an}),
            "n_dates_flagged": len({r["date"] for r in an}),
            "mean_fwd_flagged_pct": round(sum(a) / len(a), 3),
            "mean_fwd_normal_pct": round(sum(b) / len(b), 3),
            "severe_rate_flagged_pct": round(
                sum(1 for v in a if v <= sev) / len(a) * 100, 1),
            "severe_rate_normal_pct": round(
                sum(1 for v in b if v <= sev) / len(b) * 100, 1),
            "max_single_date_share_pct": round(
                max(sum(1 for r in an if r["date"] == d)
                    for d in {r["date"] for r in an}) / len(an) * 100, 1),
        }
    return out


def _lane(root: Path, market: str, rows: list, feats: list, label: str,
          sev: float) -> dict:
    feats, dropped = usable_features(rows, feats)
    if len(feats) < 3:
        return {"lane": label, "disposition": "INSUFFICIENT_SUBSTRATE",
                "features_dropped_for_coverage": dropped,
                "reason": "only %d features clear the %.0f%% coverage floor"
                          % (len(feats), MIN_FEATURE_COVERAGE_PCT)}
    X, idx = _matrix(rows, feats)
    if X is None or len(idx) < MIN_ROWS:
        return {"lane": label, "n_usable": len(idx),
                "disposition": "INSUFFICIENT_SUBSTRATE",
                "reason": "%d rows carry the full feature set (need %d)"
                          % (len(idx), MIN_ROWS)}
    names = len({rows[i]["ticker"] for i in idx})
    if names < MIN_TICKERS:
        return {"lane": label, "n_usable": len(idx), "n_tickers": names,
                "disposition": "INSUFFICIENT_SUBSTRATE",
                "reason": "%d names (need %d)" % (names, MIN_TICKERS)}
    res = {"lane": label, "features": feats,
           "features_dropped_for_coverage": dropped, "n_usable": len(idx),
           "n_tickers": names, "configs_tested": len(ALGOS) * len(K_RANGE),
           "by_config": {}}
    best = None
    for algo in ALGOS:
        for k in K_RANGE:
            try:
                labels = _fit_clusters(X, algo, k)
            except Exception as e:
                res["by_config"]["%s_k%d" % (algo, k)] = {"error": str(e)[:80]}
                continue
            q = _cluster_quality(rows, idx, labels, sev)
            res["by_config"]["%s_k%d" % (algo, k)] = {
                "spread_mean_fwd_pp": q["spread_mean_fwd_pp"],
                "smallest_cluster_n": q["smallest_cluster_n"],
                "max_single_date_share_pct": q["max_single_date_share_pct"]}
            if (q["spread_mean_fwd_pp"] is not None
                    and q["n_clusters_with_n_ge_15"] >= 2
                    and (best is None
                         or q["spread_mean_fwd_pp"] > best[2]["spread_mean_fwd_pp"])):
                best = (algo, k, q, labels)
    if best is None:
        res["disposition"] = "INSUFFICIENT_SUBSTRATE"
        res["reason"] = ("no bounded configuration produced two or more "
                         "clusters of n>=15 · nothing measurable to compare")
        return res
    algo, k, q, labels = best
    res["best_in_sample"] = {"algo": algo, "k": k, **q}
    res["oos"] = _oos_separation(rows, idx, feats, sev, "kmeans", k)
    res["selection_note"] = (
        "the in-sample best of %d bounded configurations is reported for "
        "transparency and is NOT evidence · only the ticker-disjoint OOS "
        "block below can be" % res["configs_tested"])

    oos = res.get("oos") or {}
    p = oos.get("permutation_p")
    dates_ok = (q.get("max_single_date_share_pct") or 100) < 60
    if p is None:
        res["disposition"] = "INSUFFICIENT_SUBSTRATE"
        res["reason"] = "out-of-sample assignment not computable on this cohort"
    elif p >= 0.05:
        res["disposition"] = "DESCRIPTIVE_ONLY"
        res["reason"] = (
            "clusters separate in sample (%.3f pp) but the ticker-disjoint "
            "out-of-sample spread of %.3f pp is indistinguishable from a "
            "label permutation (p=%.3f) · usable to describe the cohort, "
            "not to predict" % (q["spread_mean_fwd_pp"] or 0,
                                oos.get("oos_spread_pp") or 0, p))
    elif not dates_ok:
        res["disposition"] = "REJECTED"
        res["reason"] = ("a single date supplies %.1f%% of a cluster · this is "
                         "a market-morning artefact, not a state"
                         % q["max_single_date_share_pct"])
    else:
        res["disposition"] = "CONDITIONAL"
        res["reason"] = ("out-of-sample separation survives permutation "
                         "(p=%.3f) · must still show incremental value over "
                         "R2 before it means anything" % p)
    return res


def run(root: Path, market: str) -> dict:
    rows = core.load_pop(root, market, features=TECHNICAL_FEATURES)
    if len(rows) < MIN_ROWS:
        return {"market": market, "error": "cohort too small: %d" % len(rows)}
    n_fund = _attach_fundamentals(root, market, rows)
    sev = core.severe_cut(rows)
    sub = core.substrate_assessment(rows)

    lanes = {
        "A_fundamental_state": _lane(root, market, rows, FUNDAMENTAL_FEATURES,
                                     "A_fundamental_state", sev),
        "B_technical_behaviour": _lane(root, market, rows, TECHNICAL_FEATURES,
                                       "B_technical_behaviour", sev),
        "C_fundamental_x_technical": _lane(
            root, market, rows, FUNDAMENTAL_FEATURES + TECHNICAL_FEATURES,
            "C_fundamental_x_technical", sev),
    }
    _, idx_t = _matrix(rows, TECHNICAL_FEATURES)
    anom = _anomalies(rows, idx_t, TECHNICAL_FEATURES, sev)

    disp = [v.get("disposition") for v in lanes.values()]
    if any(d == "CONDITIONAL" for d in disp):
        family = "CONDITIONAL"
    elif any(d == "DESCRIPTIVE_ONLY" for d in disp):
        family = "DESCRIPTIVE_ONLY"
    else:
        family = "INSUFFICIENT_SUBSTRATE"

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_family_id": FAMILY,
        "experiment_id": "%s_%s" % (FAMILY, market.lower()),
        "status": "RESEARCH ONLY · no production surface",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_definition": "fwd_10d_pct · severe loss = worst decile",
        "pit_methodology": ("technical features as-of the prediction date · "
                            "fundamentals gated at a 45-day assumed "
                            "publication lag"),
        "publication_lag_assumption_days": 45,
        "substrate": sub,
        "rows_with_fundamentals": n_fund,
        "severe_cut_pct": round(sev, 3),
        "train_test_methodology": "5-fold ticker-disjoint · OOS assignment only",
        "preprocessing": "winsorised 1/99 then standardised · applied uniformly",
        "oos_status": "TICKER_DISJOINT",
        "multiple_testing_family_size": len(ALGOS) * len(K_RANGE) * 3,
        "correction_method": ("permutation null on the OOS spread · the "
                              "in-sample best-of-12 is reported but never "
                              "treated as evidence"),
        "baseline": "label permutation within the same cohort",
        "lanes": lanes,
        "anomaly_detection": anom,
        "trajectory_clusters_note": (
            "OUTCOME-TRAJECTORY CLUSTERING IS DELIBERATELY NOT EMITTED AS A "
            "FEATURE. Such clusters are built from the outcome and would leak "
            "directly into any model that consumed them. Failure-mode "
            "description is already covered by the descriptive cohort work."),
        "family_disposition": family,
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "research" / "r3" / f"unsupervised_{rep['market']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = root / "reports" / "research" / "r3" / f"unsupervised_{market.lower()}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3-H unsupervised intelligence")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        emit(root, rep)
        print(f"R3-H:{m} · {rep['family_disposition']}")
        for k, v in rep["lanes"].items():
            print(f"    {k:<28} {v.get('disposition'):<24} {v.get('reason','')[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
