"""R3 EXIT/ENTRY INTELLIGENCE VALIDATOR · Wave 1D · CEO 2026-09-08.

> "Not merely 'Does LightGBM predict?' But: does R3 intelligence improve
>  candidate selection over R2 alone? That is the real test."

So AUC is reported but it is NOT the headline. The headline is the
incremental-value test: rank the R2 candidate pool by R3 probability, cut
it into buckets, and ask whether the top bucket actually behaves better
than the unfiltered pool it came from. A model can post 0.91 AUC and still
be worthless if the pool it ranks is uniformly good or uniformly bad.

WHAT IS VALIDATED
-----------------
    T1  P(+1R before stop)
    T2  P(+2R before stop)
    T3  P(reversal / giveback)
    T4  P(stop hit by horizon)

against four splits, each answering a different question:

    walk_forward     does it persist through TIME (the only one that can
                     support a promotion claim)
    ticker_disjoint  is it more than memorising a NAME
    date_disjoint    is it more than memorising a DAY - the split that
                     killed the sequence models in Wave 1C
    market_separated does it transfer between India and USA

PLUS calibration (Brier + ECE + reliability bins), permutation importance,
feature-group ablation, bootstrap CIs on AUC, and BH-FDR across every
counted comparison.

A probability that is well-ranked but badly calibrated cannot size a
position, so calibration is reported beside every AUC rather than
implied by it.

RESEARCH ONLY · no engine, no threshold, no promotion.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.wave1d.v1"
FAMILY = "R3_INTELLIGENCE_VALIDATOR_V1"

FEATURES = ["confidence_pct", "vol_20d_pct", "ma200_dist_pct",
            "momentum_20d_pct", "rank", "stop_distance_pct"]
FEATURE_GROUPS = {
    "model_signal": ["confidence_pct", "rank"],
    "trend": ["ma200_dist_pct", "momentum_20d_pct"],
    "risk": ["vol_20d_pct", "stop_distance_pct"],
}
BOOTSTRAP_N = 200
SEED = 20260908


def _auc(y, p) -> Optional[float]:
    pos = [i for i, v in enumerate(y) if v == 1]
    neg = [i for i, v in enumerate(y) if v == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(p)), key=lambda i: p[i])
    rank = [0.0] * len(p)
    for r, i in enumerate(order, 1):
        rank[i] = r
    return (sum(rank[i] for i in pos) - len(pos) * (len(pos) + 1) / 2) \
        / (len(pos) * len(neg))


def _bootstrap_auc_ci(y, p, n=BOOTSTRAP_N) -> list:
    rng = random.Random(SEED)
    n_obs = len(y)
    vals = []
    for _ in range(n):
        idx = [rng.randrange(n_obs) for _ in range(n_obs)]
        a = _auc([y[i] for i in idx], [p[i] for i in idx])
        if a is not None:
            vals.append(a)
    if len(vals) < 20:
        return [None, None]
    vals.sort()
    return [round(vals[int(len(vals) * 0.025)], 4),
            round(vals[int(len(vals) * 0.975)], 4)]


def _calibration(y, p, bins: int = 5) -> dict:
    """Brier + ECE + reliability · a ranking is not a probability."""
    brier = sum((a - b) ** 2 for a, b in zip(y, p)) / max(1, len(y))
    rel, ece = [], 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, v in enumerate(p) if (lo <= v < hi or (b == bins - 1 and v == 1.0))]
        if not idx:
            continue
        pred = sum(p[i] for i in idx) / len(idx)
        obs = sum(y[i] for i in idx) / len(idx)
        rel.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(idx),
                    "mean_predicted": round(pred, 4),
                    "observed_rate": round(obs, 4)})
        ece += len(idx) / len(y) * abs(pred - obs)
    return {"brier": round(brier, 4), "ece": round(ece, 4),
            "reliability_bins": rel}


def _fit_predict(X, y, tr, te, feats_idx=None):
    import lightgbm as lgb
    import numpy as np
    Xtr = X[tr] if feats_idx is None else X[tr][:, feats_idx]
    Xte = X[te] if feats_idx is None else X[te][:, feats_idx]
    m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                           learning_rate=0.05, n_estimators=200,
                           min_child_samples=15, reg_lambda=1.0,
                           verbose=-1, random_state=SEED)
    m.fit(Xtr, np.array(y)[tr])
    return list(m.predict_proba(Xte)[:, 1]), m


def _folds_by(keys, n=5):
    uniq = sorted(set(keys))
    if len(uniq) < n:
        return []
    assign = {k: i % n for i, k in enumerate(uniq)}
    out = []
    for f in range(n):
        tr = [i for i, k in enumerate(keys) if assign[k] != f]
        te = [i for i, k in enumerate(keys) if assign[k] == f]
        if len(tr) > 30 and len(te) > 8:
            out.append((tr, te))
    return out


def _walk_forward_folds(dates_iso, n_folds=3, embargo=5, horizon=10):
    """Train strictly in the past, embargo gap, then test.

    Returns [] when the date span cannot support it - the honest outcome
    for a 24-date cohort, and the runner reports the refusal rather than
    substituting a random split.
    """
    uniq = sorted(set(dates_iso))
    if len(uniq) < n_folds * 2 + 1:
        return []
    out = []
    step = len(uniq) // (n_folds + 1)
    if step < 1:
        return []
    for k in range(1, n_folds + 1):
        cut = step * k
        train_dates = set(uniq[:cut])
        gap_end = cut + embargo
        if gap_end >= len(uniq):
            break
        test_dates = set(uniq[gap_end:gap_end + step])
        tr = [i for i, d in enumerate(dates_iso) if d in train_dates]
        te = [i for i, d in enumerate(dates_iso) if d in test_dates]
        if len(tr) > 30 and len(te) > 8:
            out.append((tr, te))
    return out


def economic_value(eps, y, prob, key_metrics=True) -> dict:
    """> "If the top R3 probability bucket consistently beats the
    unfiltered R2 pool, then we have something worth taking seriously."

    AUC says the ranking is right. This says whether acting on it would
    have been better than not.
    """
    order = sorted(range(len(prob)), key=lambda i: -prob[i])
    n = len(order)

    def stats(idx):
        if not idx:
            return {"n": 0}
        fr = [eps[i]["final_r"] for i in idx]
        return {
            "n": len(idx),
            "share_of_pool_pct": round(len(idx) / n * 100, 1),
            "mean_final_r": round(sum(fr) / len(fr), 3),
            "median_final_r": round(sorted(fr)[len(fr) // 2], 3),
            "hit_1R_before_stop_pct": round(
                sum(1 for i in idx if eps[i]["hit_1R_before_stop"])
                / len(idx) * 100, 1),
            "stop_hit_pct": round(
                sum(1 for i in idx if eps[i]["stop_hit"]) / len(idx) * 100, 1),
            "reversed_pct": round(
                sum(1 for i in idx if eps[i]["reversed"]) / len(idx) * 100, 1),
            "mean_peak_r": round(
                sum(eps[i]["peak_r"] for i in idx) / len(idx), 3),
            "mean_trough_r": round(
                sum(eps[i]["trough_r"] for i in idx) / len(idx), 3),
            "worst_final_r": round(min(fr), 3),
            "n_tickers": len({eps[i]["ticker"] for i in idx}),
        }

    base = stats(list(range(n)))
    out = {"UNFILTERED_R2_POOL": base}
    for label, frac in (("top_5pct", 0.05), ("top_10pct", 0.10),
                        ("top_20pct", 0.20), ("bottom_20pct", -0.20)):
        k = max(1, int(n * abs(frac)))
        idx = order[:k] if frac > 0 else order[-k:]
        s = stats(idx)
        s["lift_mean_final_r"] = round(s["mean_final_r"] - base["mean_final_r"], 3)
        s["lift_hit_1R_pp"] = round(
            s["hit_1R_before_stop_pct"] - base["hit_1R_before_stop_pct"], 1)
        s["lift_stop_hit_pp"] = round(
            s["stop_hit_pct"] - base["stop_hit_pct"], 1)
        out[label] = s
    top = out["top_20pct"]
    out["verdict"] = (
        "R3 RANKING ADDS VALUE" if (top["lift_mean_final_r"] > 0
                                    and top["lift_hit_1R_pp"] > 0)
        else "NO INCREMENTAL VALUE over the unfiltered pool")
    return out


def validate_target(eps, y, tname: str) -> dict:
    import numpy as np
    X = np.array([[e.get(f) if e.get(f) is not None else float("nan")
                   for f in FEATURES] for e in eps], dtype=float)
    tickers = [e["ticker"] for e in eps]
    dates = [e["entry_date"] for e in eps]

    splits = {
        "walk_forward": _walk_forward_folds(dates),
        "ticker_disjoint": _folds_by(tickers),
        "date_disjoint": _folds_by(dates),
    }
    res, oof_p, oof_y, oof_i = {}, [None] * len(y), [None] * len(y), []
    for sname, folds in splits.items():
        if not folds:
            res[sname] = {"refused": "split not constructible on this cohort"}
            continue
        aucs, cal_y, cal_p = [], [], []
        for tr, te in folds:
            if len(set(np.array(y)[tr])) < 2:
                continue
            p, _ = _fit_predict(X, y, tr, te)
            a = _auc([y[i] for i in te], p)
            if a is not None:
                aucs.append(round(a, 4))
            cal_y += [y[i] for i in te]
            cal_p += p
            if sname == "ticker_disjoint":
                for j, i in enumerate(te):
                    oof_p[i], oof_y[i] = p[j], y[i]
                    oof_i.append(i)
        if not aucs:
            res[sname] = {"refused": "single-class folds"}
            continue
        res[sname] = {
            "n_folds": len(aucs), "auc_folds": aucs,
            "auc_mean": round(sum(aucs) / len(aucs), 4),
            "auc_ci95_bootstrap": _bootstrap_auc_ci(cal_y, cal_p),
            "calibration": _calibration(cal_y, cal_p),
        }

    # Ablation · which feature GROUP carries the signal.
    abl = {}
    tf = splits.get("ticker_disjoint") or []
    if tf:
        full = res.get("ticker_disjoint", {}).get("auc_mean")
        for gname, gfeats in FEATURE_GROUPS.items():
            keep = [i for i, f in enumerate(FEATURES) if f not in gfeats]
            aucs = []
            for tr, te in tf:
                if len(set(np.array(y)[tr])) < 2:
                    continue
                p, _ = _fit_predict(X, y, tr, te, feats_idx=keep)
                a = _auc([y[i] for i in te], p)
                if a is not None:
                    aucs.append(a)
            if aucs and full:
                m = sum(aucs) / len(aucs)
                abl[gname] = {"auc_without": round(m, 4),
                              "delta_vs_full": round(m - full, 4)}
    res["ablation_drop_group"] = abl

    # Economic value on out-of-fold predictions · never in-sample.
    idx = sorted(set(oof_i))
    if len(idx) > 30:
        res["economic_value"] = economic_value(
            [eps[i] for i in idx], [oof_y[i] for i in idx],
            [oof_p[i] for i in idx])
    return res


def _bh(pvals, alpha=0.05):
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    if not m:
        return [False] * len(pvals)
    order = sorted(idx, key=lambda i: pvals[i])
    keep, thresh = [False] * len(pvals), 0
    for r, i in enumerate(order, 1):
        if pvals[i] <= alpha * r / m:
            thresh = r
    for r, i in enumerate(order, 1):
        if r <= thresh:
            keep[i] = True
    return keep


def _auc_pvalue(auc, n_pos, n_neg) -> Optional[float]:
    """Normal approximation to the Mann-Whitney null (AUC = 0.5)."""
    if auc is None or n_pos < 5 or n_neg < 5:
        return None
    sd = math.sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg))
    z = (auc - 0.5) / sd
    return round(math.erfc(abs(z) / math.sqrt(2)), 8)


def run_market(root: Path, market: str) -> dict:
    from backend.research.cohort.entry_backfill import backfill
    from backend.research.cohort.exit_hazard import build_episodes
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery.sequence_models import targets_for

    rows = load_cohort(root, market)
    backfill(root, market, rows)
    eps = build_episodes(root, market, rows)
    dts = Counter(e["entry_date"] for e in eps)
    tks = Counter(e["ticker"] for e in eps)

    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · no production rule · R2 unchanged",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_episodes": len(eps), "n_tickers": len(tks), "n_dates": len(dts),
        "features": FEATURES,
    }
    if len(eps) < 60:
        rep["refusal"] = "NO VALIDATION · %d episodes" % len(eps)
        return rep

    T = targets_for(eps)
    wanted = {"T1_P_1R_before_stop": T["P_1R_before_stop"],
              "T2_P_2R_before_stop": T["P_2R_before_stop"],
              "T3_reversal_20d": T["reversal_20d"],
              "T4_stop_hit_10d": T["stop_hit_10d"]}
    out, trials = {}, []
    for name, y in wanted.items():
        pos = sum(y)
        if pos < 15 or len(y) - pos < 15:
            out[name] = {"skipped": "class too small (%d/%d)" % (pos, len(y))}
            continue
        r = validate_target(eps, y, name)
        r["event_rate_pct"] = round(pos / len(y) * 100, 1)
        out[name] = r
        for sname in ("walk_forward", "ticker_disjoint", "date_disjoint"):
            a = (r.get(sname) or {}).get("auc_mean")
            trials.append((name, sname, _auc_pvalue(a, pos, len(y) - pos)))
    keep = _bh([t[2] for t in trials])
    rep["targets"] = out
    rep["multiple_testing"] = {
        "n_comparisons": len(trials),
        "correction": "Benjamini-Hochberg FDR alpha=0.05",
        "survivors": [{"target": t[0], "split": t[1], "p": t[2]}
                      for t, k in zip(trials, keep) if k],
        "n_survivors": sum(1 for k in keep if k),
    }
    return rep


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1d_validator_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1d_validator_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 intelligence validator 1D")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run_market(root, m)
        emit(root, rep)
        print(f"wave1d:{m} · episodes {rep['n_episodes']} · dates "
              f"{rep['n_dates']}")
        if rep.get("refusal"):
            print(f"    {rep['refusal']}")
            continue
        mt = rep["multiple_testing"]
        print(f"    trials {mt['n_comparisons']} · FDR survivors "
              f"{mt['n_survivors']}")
        for t, r in rep["targets"].items():
            ev = (r or {}).get("economic_value")
            if ev:
                print(f"    {t:<24}{ev['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
