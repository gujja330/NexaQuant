"""R3 VALIDATOR · WAVE 1D-C · CEO 2026-09-08.

Repairs the three confounds that invalidated Wave 1D's headline AUCs.
Wave 1D's numbers are preserved as audit history, not erased - but they
are not evidence, and this module exists so that a corrected number can
replace them.

CONFOUND 1 · SPLIT CONTAMINATION
---------------------------------
Ticker-disjoint folds share DATES. Date-disjoint folds share TICKERS.
Neither controls both, which is why the same target scored 0.768 under
one and 0.974 under the other - a 20-point gap that cannot exist if the
signal is durable.

Fixed by a JOINT holdout: the test block is episodes whose ticker AND
date both fall in fold k; the train block excludes both. Nothing shared
on either axis. It discards the off-diagonal episodes, so it is smaller
and more honest.

CONFOUND 2 · HALF THE STOPS ARE A RENDERING DEFAULT
----------------------------------------------------
282 of 547 India episodes (51.6%) and 35 of 79 USA episodes (44.3%) have
stop_distance == exactly 5.00% - `detail_xlsx`'s documented fallback
("engine only populates stop/T1/T2 for actionable BUYs · derive standard
defaults"). Those are not risk decisions and behave differently:
default-stop rows reached +1R 34.4% of the time versus 24.2% for
real-stop rows, and the ordering INVERTS on +2R.

Fixed by segmenting. REAL_STOP is the cohort that can speak about
dynamic-risk behaviour; DEFAULT_STOP is reported separately and never
merged into a claim about stop policy.

CONFOUND 3 · THE R-MULTIPLE TAUTOLOGY
--------------------------------------
R = stop_distance_pct is the DENOMINATOR of the +1R/+2R definition, so a
tight stop mechanically reaches +1R more easily. stop_distance_pct alone,
with no model, scores AUC 0.853 on P(+2R) and 0.700 on P(+1R).

Fixed by adding ABSOLUTE-return race targets (+3%/-3%, +5%/-5%,
+10%/-5%) whose definition contains no stop term at all. If a signal
survives on absolute targets it is not an artefact of the stop width.

RESEARCH ONLY · no engine, no threshold, no promotion.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.wave1dc.v1"
FAMILY = "R3_VALIDATOR_WAVE1DC"

DEFAULT_STOP_PCT = 5.0
DEFAULT_TOL = 0.01

# Absolute races · no stop term in the definition.
ABS_TARGETS = [("abs_3_before_-3", 3.0, -3.0),
               ("abs_5_before_-5", 5.0, -5.0),
               ("abs_10_before_-5", 10.0, -5.0)]

FEATURES = ["confidence_pct", "vol_20d_pct", "ma200_dist_pct",
            "momentum_20d_pct", "rank"]      # stop_distance DELIBERATELY out
FEATURES_WITH_STOP = FEATURES + ["stop_distance_pct"]
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
    return round((sum(rank[i] for i in pos) - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)), 4)


def _brier(y, p):
    return round(sum((a - b) ** 2 for a, b in zip(y, p)) / max(1, len(y)), 4)


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def absolute_race(dates, closes, entry_date, entry: float,
                  up_pct: float, dn_pct: float, max_days: int = 20):
    """Did price reach +up% before -dn%? Contains no stop term."""
    start = None
    for i, d in enumerate(dates):
        if d > entry_date:
            start = i
            break
    if start is None:
        return None
    for px in closes[start:start + max_days]:
        r = (px / entry - 1.0) * 100.0
        if r >= up_pct:
            return 1
        if r <= dn_pct:
            return 0
    return 0            # neither reached · counted as a non-win


def build(root: Path, market: str) -> dict:
    from backend.research.cohort.entry_backfill import backfill
    from backend.research.cohort.exit_hazard import build_episodes
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery.temporal import _load_series

    rows = load_cohort(root, market)
    backfill(root, market, rows)
    eps = build_episodes(root, market, rows)

    cache = {}
    for e in eps:
        e["is_default_stop"] = int(
            abs(e["stop_distance_pct"] - DEFAULT_STOP_PCT) < DEFAULT_TOL)
        t, d = e["ticker"], _d(e["entry_date"])
        if t not in cache:
            cache[t] = _load_series(root, market, t)
        s = cache[t]
        if s is None or d is None:
            continue
        # Entry reference · the close on or before the prediction date.
        hi = -1
        for i, dd in enumerate(s[0]):
            if dd <= d:
                hi = i
            else:
                break
        if hi < 0:
            continue
        entry = s[1][hi]
        for name, up, dn in ABS_TARGETS:
            e[name] = absolute_race(s[0], s[1], d, entry, up, dn)
    return eps


def joint_folds(eps: list, n: int = 4):
    """Ticker AND date both held out · nothing shared on either axis."""
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
        if len(tr) >= 40 and len(te) >= 10:
            out.append((tr, te))
    return out


def _fit(X, y, tr, te):
    import lightgbm as lgb
    import numpy as np
    m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                           learning_rate=0.05, n_estimators=200,
                           min_child_samples=15, reg_lambda=1.0,
                           verbose=-1, random_state=SEED)
    m.fit(X[tr], np.array(y)[tr])
    return list(m.predict_proba(X[te])[:, 1])


def evaluate(eps: list, target: str, feats: list, label: str) -> dict:
    import numpy as np
    y = [e.get(target) for e in eps]
    keep = [i for i, v in enumerate(y) if v is not None]
    if len(keep) < 60:
        return {"skipped": "n=%d" % len(keep)}
    eps = [eps[i] for i in keep]
    y = [y[i] for i in keep]
    pos = sum(y)
    if pos < 12 or len(y) - pos < 12:
        return {"skipped": "class too small (%d/%d)" % (pos, len(y))}
    X = np.array([[e.get(f) if e.get(f) is not None else float("nan")
                   for f in feats] for e in eps], dtype=float)
    folds = joint_folds(eps)
    if not folds:
        return {"refused": "joint ticker x date folds not constructible"}

    aucs, cy, cp, base = [], [], [], []
    for tr, te in folds:
        if len(set(np.array(y)[tr])) < 2:
            continue
        p = _fit(X, y, tr, te)
        a = _auc([y[i] for i in te], p)
        if a is not None:
            aucs.append(a)
        cy += [y[i] for i in te]
        cp += p
        # Baseline · volatility. Strength is max(a, 1-a): an AUC of 0.21
        # means the heuristic predicts strongly in the OPPOSITE direction
        # and is a 0.79 baseline once its sign is flipped. Scoring it as
        # 0.21 would have let the model "beat" a baseline stronger than
        # itself.
        vb = _auc([y[i] for i in te],
                  [(eps[i].get("vol_20d_pct") or 0.0) for i in te])
        if vb is not None:
            base.append(max(vb, 1.0 - vb))
    if not aucs:
        return {"refused": "single-class folds"}
    return {
        "cohort": label, "features": feats,
        "n": len(y), "event_rate_pct": round(pos / len(y) * 100, 1),
        "n_folds": len(aucs),
        "n_test_episodes": sum(len(te) for _, te in folds),
        "auc_folds": aucs,
        "auc_mean": round(sum(aucs) / len(aucs), 4),
        "baseline_volatility_auc_directionless": (round(sum(base) / len(base), 4)
                                    if base else None),
        "beats_baseline": bool(base and sum(aucs) / len(aucs)
                               > sum(base) / len(base)),
        "baseline_note": "max(auc, 1-auc) · a heuristic that predicts "
                         "inversely is still a heuristic",
        "brier": _brier(cy, cp),
    }


def run_market(root: Path, market: str) -> dict:
    eps = build(root, market)
    n_def = sum(e["is_default_stop"] for e in eps)
    cohorts = {
        "ALL": eps,
        "REAL_STOP": [e for e in eps if not e["is_default_stop"]],
        "DEFAULT_STOP": [e for e in eps if e["is_default_stop"]],
    }
    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · corrects Wave 1D confounds · R2 unchanged",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_episodes": len(eps),
        "n_default_stop": n_def,
        "default_stop_pct": round(n_def / max(1, len(eps)) * 100, 1),
        "split": "JOINT ticker x date holdout · nothing shared on either axis",
        "confounds_corrected": [
            "split contamination · joint ticker x date holdout",
            "synthetic 5.0%% default stops segmented (%d of %d)"
            % (n_def, len(eps)),
            "R-multiple tautology · absolute-return targets added",
        ],
    }
    results = {}
    for cname, ce in cohorts.items():
        if len(ce) < 60:
            results[cname] = {"skipped": "n=%d" % len(ce)}
            continue
        block = {}
        # R-multiple targets · WITHOUT stop_distance as a feature, so the
        # tautology cannot re-enter through the feature set.
        for t in ("hit_1R_before_stop", "hit_2R_before_stop"):
            for e in ce:
                e[t + "_i"] = 1 if e[t] else 0
            block[t] = evaluate(ce, t + "_i", FEATURES, cname)
        # Absolute targets · no stop term anywhere in the definition.
        for name, _, _ in ABS_TARGETS:
            block[name] = evaluate(ce, name, FEATURES, cname)
        results[cname] = block
    rep["results"] = results

    surv = []
    for cname, block in results.items():
        if not isinstance(block, dict) or block.get("skipped"):
            continue
        for tname, r in block.items():
            if isinstance(r, dict) and r.get("beats_baseline") \
                    and (r.get("auc_mean") or 0) > 0.6:
                surv.append({"cohort": cname, "target": tname,
                             "auc": r["auc_mean"],
                             "baseline": r["baseline_volatility_auc_directionless"],
                             "n": r["n"]})
    rep["survivors"] = sorted(surv, key=lambda d: -d["auc"])
    rep["verdict"] = (
        "SIGNAL SURVIVES the corrected split on %d target/cohort pairs"
        % len(surv) if surv else
        "NO SIGNAL SURVIVES the joint ticker x date holdout")
    return rep


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1dc_validator_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"wave1dc_validator_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Wave 1D-C corrected validator")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run_market(root, m)
        emit(root, rep)
        print(f"wave1dc:{m} · episodes {rep['n_episodes']} · default-stop "
              f"{rep['default_stop_pct']}% · {rep['verdict']}")
        for s in rep["survivors"][:6]:
            print(f"    {s['cohort']:<13}{s['target']:<22}AUC {s['auc']} "
                  f"vs baseline {s['baseline']} · n={s['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
