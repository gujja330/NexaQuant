"""R3 VALIDATOR · WAVE 1D-E · CEO 2026-09-08.

> "Does R3 still identify better R2 candidates when the target cannot
>  mathematically depend on the stop width?"

Until that answer is yes, the apparent R3-G edge is unresolved.

THE EXPANSION THAT MATTERS
--------------------------
Wave 1D-C could only use 265 India episodes because it needed a real stop.
But an ABSOLUTE race - did price reach +3% before -3%? - contains no stop
term at all, so it does not need one. That releases the whole cohort:

    stop-bearing episodes   India 265 REAL_STOP  ·  USA  44
    full cohort (no stop)   India 725            ·  USA 1156

So the question is asked on ~2.7x more India rows and ~26x more USA rows
than 1D-C could reach, and on a target that is definitionally immune to
the confound.

CONTRACT
--------
* `stop_distance_pct` is NOT in the feature contract. It cannot re-enter.
* Joint ticker x date holdout · nothing shared on either axis.
* Three trivial baselines, each scored max(auc, 1-auc): an inverse
  predictor is still a predictor.
* BH-FDR across the complete predefined family, counted before any result
  is read.
* Economic value computed ONLY for targets that survive correction.

TARGETS · absolute races over three windows
--------------------------------------------
    +3% before -3%    over 5 / 10 / 20 trading days
    +5% before -5%
    +10% before -5%   asymmetric · the payoff shape R2 actually wants

RESEARCH ONLY · no engine, no threshold, no promotion.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.wave1de.v1"
FAMILY = "R3_VALIDATOR_WAVE1DE"

# stop_distance_pct is DELIBERATELY ABSENT and must stay absent.
FEATURES = ["confidence_pct", "vol_20d_pct", "ma200_dist_pct",
            "ma50_dist_pct", "momentum_20d_pct", "momentum_60d_pct",
            "rsi_14", "rank"]

RACES = [("3_3", 3.0, -3.0), ("5_5", 5.0, -5.0), ("10_5", 10.0, -5.0)]
WINDOWS = [5, 10, 20]
SEED = 20260908
MIN_TEST = 25


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _auc(y, p) -> Optional[float]:
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


def _auc_p(auc, n_pos, n_neg) -> Optional[float]:
    if auc is None or n_pos < 8 or n_neg < 8:
        return None
    sd = math.sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg))
    return round(math.erfc(abs((auc - 0.5) / sd) / math.sqrt(2)), 8)


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


def build(root: Path, market: str) -> list:
    """Full cohort · no stop required. One row per (ticker, date)."""
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery.temporal import _load_series

    rows = load_cohort(root, market)
    seen, cache, out = set(), {}, []
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        d = _d(r.get("prediction_date"))
        if not t or d is None or (t, d) in seen:
            continue
        seen.add((t, d))
        if t not in cache:
            cache[t] = _load_series(root, market, t)
        s = cache[t]
        if s is None:
            continue
        dates, closes = s
        hi = -1
        for i, dd in enumerate(dates):
            if dd <= d:
                hi = i
            else:
                break
        if hi < 0 or hi + 1 >= len(closes):
            continue
        entry = closes[hi]
        e = {"ticker": t, "entry_date": d.isoformat()}
        for f in FEATURES:
            e[f] = _num(r.get(f))
        fwd = closes[hi + 1:hi + 1 + max(WINDOWS)]
        if len(fwd) < min(WINDOWS):
            continue
        for name, up, dn in RACES:
            for w in WINDOWS:
                seg = fwd[:w]
                if len(seg) < w:
                    e[f"race_{name}_{w}d"] = None
                    continue
                res = 0
                for px in seg:
                    ret = (px / entry - 1.0) * 100.0
                    if ret >= up:
                        res = 1
                        break
                    if ret <= dn:
                        res = 0
                        break
                e[f"race_{name}_{w}d"] = res
        # Realised return for the economic-value test.
        e["fwd_return_10d_pct"] = (round((fwd[min(9, len(fwd) - 1)] / entry - 1)
                                         * 100, 4))
        out.append(e)
    return out


def joint_folds(eps: list, n: int = 4):
    tk = sorted({e["ticker"] for e in eps})
    dt = sorted({e["entry_date"] for e in eps})
    ta = {t: i % n for i, t in enumerate(tk)}
    da = {d: i % n for i, d in enumerate(dt)}
    out = []
    for k in range(n):
        te = [i for i, e in enumerate(eps)
              if ta[e["ticker"]] == k and da[e["entry_date"]] == k]
        tr = [i for i, e in enumerate(eps)
              if ta[e["ticker"]] != k and da[e["entry_date"]] != k]
        if len(tr) >= 60 and len(te) >= MIN_TEST:
            out.append((tr, te))
    return out


def _fit(X, y, tr, te):
    import lightgbm as lgb
    import numpy as np
    m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                           learning_rate=0.05, n_estimators=200,
                           min_child_samples=20, reg_lambda=1.0,
                           verbose=-1, random_state=SEED)
    m.fit(X[tr], np.array(y)[tr])
    return list(m.predict_proba(X[te])[:, 1])


def evaluate(eps: list, target: str) -> dict:
    import numpy as np
    y_all = [e.get(target) for e in eps]
    keep = [i for i, v in enumerate(y_all) if v is not None]
    sub = [eps[i] for i in keep]
    y = [y_all[i] for i in keep]
    pos = sum(y)
    if len(y) < 120 or pos < 20 or len(y) - pos < 20:
        return {"skipped": "n=%d pos=%d" % (len(y), pos)}
    X = np.array([[e.get(f) if e.get(f) is not None else float("nan")
                   for f in FEATURES] for e in sub], dtype=float)
    folds = joint_folds(sub)
    if not folds:
        return {"refused": "joint ticker x date folds not constructible"}

    aucs, base = [], {"volatility": [], "momentum": [], "trend": []}
    oof_p, oof_i = {}, []
    for tr, te in folds:
        if len(set(np.array(y)[tr])) < 2:
            continue
        p = _fit(X, y, tr, te)
        a = _auc([y[i] for i in te], p)
        if a is None:
            continue
        aucs.append(a)
        for j, i in enumerate(te):
            oof_p[i] = p[j]
            oof_i.append(i)
        for bname, feat in (("volatility", "vol_20d_pct"),
                            ("momentum", "momentum_20d_pct"),
                            ("trend", "ma200_dist_pct")):
            b = _auc([y[i] for i in te],
                     [(sub[i].get(feat) or 0.0) for i in te])
            if b is not None:
                base[bname].append(max(b, 1.0 - b))
    if not aucs:
        return {"refused": "single-class folds"}
    bmeans = {k: (round(sum(v) / len(v), 4) if v else None)
              for k, v in base.items()}
    best_b = max((v for v in bmeans.values() if v is not None), default=None)
    m_auc = round(sum(aucs) / len(aucs), 4)
    return {
        "n": len(y), "event_rate_pct": round(pos / len(y) * 100, 1),
        "n_folds": len(aucs), "n_test": len(oof_i),
        "auc_mean": m_auc, "auc_folds": aucs,
        "baselines_directionless": bmeans,
        "best_baseline": best_b,
        "beats_best_baseline": bool(best_b is not None and m_auc > best_b),
        "p_value": _auc_p(m_auc, pos, len(y) - pos),
        "_oof": {"idx": oof_i, "p": [oof_p[i] for i in oof_i],
                 "y": [y[i] for i in oof_i],
                 "ret": [sub[i]["fwd_return_10d_pct"] for i in oof_i],
                 "tick": [sub[i]["ticker"] for i in oof_i]},
    }


def economic_value(r: dict) -> dict:
    o = r["_oof"]
    order = sorted(range(len(o["p"])), key=lambda i: -o["p"][i])
    n = len(order)

    def stats(idx):
        ret = [o["ret"][i] for i in idx]
        return {"n": len(idx),
                "mean_return_pct": round(sum(ret) / len(ret), 3),
                "hit_rate_pct": round(sum(o["y"][i] for i in idx)
                                      / len(idx) * 100, 1),
                "n_tickers": len({o["tick"][i] for i in idx})}
    base = stats(list(range(n)))
    out = {"UNFILTERED_R2_POOL": base}
    for lbl, frac in (("top_10pct", .10), ("top_20pct", .20),
                      ("bottom_20pct", -.20)):
        k = max(1, int(n * abs(frac)))
        s = stats(order[:k] if frac > 0 else order[-k:])
        s["lift_return_pp"] = round(s["mean_return_pct"]
                                    - base["mean_return_pct"], 3)
        s["lift_hit_pp"] = round(s["hit_rate_pct"] - base["hit_rate_pct"], 1)
        out[lbl] = s
    t = out["top_20pct"]
    out["verdict"] = ("ADDS VALUE over the unfiltered pool"
                      if t["lift_return_pp"] > 0 and t["lift_hit_pp"] > 0
                      else "NO incremental value")
    return out


def run_market(root: Path, market: str) -> dict:
    eps = build(root, market)
    tks = Counter(e["ticker"] for e in eps)
    dts = Counter(e["entry_date"] for e in eps)
    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · absolute targets · no stop term anywhere",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": ("does R3 still identify better R2 candidates when the "
                     "target cannot mathematically depend on stop width?"),
        "n_rows": len(eps), "n_tickers": len(tks), "n_dates": len(dts),
        "features": FEATURES,
        "stop_distance_in_features": "stop_distance_pct" in FEATURES,
        "split": "JOINT ticker x date holdout",
    }
    if len(eps) < 150:
        rep["refusal"] = "NO VALIDATION · %d rows" % len(eps)
        return rep

    results, trials = {}, []
    for name, _, _ in RACES:
        for w in WINDOWS:
            t = f"race_{name}_{w}d"
            r = evaluate(eps, t)
            results[t] = r
            if "auc_mean" in r:
                trials.append((t, r["p_value"]))
    keep = _bh([p for _, p in trials])
    survivors = [t for (t, _), k in zip(trials, keep) if k]

    # Economic value ONLY for targets that survive correction.
    for t in survivors:
        r = results[t]
        if r.get("beats_best_baseline"):
            r["economic_value"] = economic_value(r)
    for r in results.values():
        r.pop("_oof", None)

    rep["results"] = results
    rep["multiple_testing"] = {
        "n_comparisons": len(trials),
        "correction": "Benjamini-Hochberg FDR alpha=0.05",
        "survivors": survivors, "n_survivors": len(survivors),
    }
    real = [t for t in survivors
            if results[t].get("beats_best_baseline")
            and (results[t].get("economic_value") or {}).get("verdict", "")
            .startswith("ADDS")]
    rep["answer"] = (
        "YES · signal survives on an absolute target with no stop term: %s"
        % ", ".join(real) if real else
        "NO · no absolute-return target both beats its baseline and adds "
        "incremental value · the R-multiple edge remains UNRESOLVED")
    return rep


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1de_validator_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1de_validator_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Wave 1D-E absolute-target test")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run_market(root, m)
        emit(root, rep)
        print(f"wave1de:{m} · rows {rep['n_rows']} · tickers "
              f"{rep['n_tickers']} · dates {rep['n_dates']}")
        if rep.get("refusal"):
            print(f"    {rep['refusal']}")
            continue
        mt = rep["multiple_testing"]
        print(f"    trials {mt['n_comparisons']} · FDR survivors "
              f"{mt['n_survivors']}")
        print(f"    ANSWER: {rep['answer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
