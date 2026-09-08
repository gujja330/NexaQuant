"""R3-G · EXIT HAZARD / SURVIVAL RESEARCH · CEO 2026-09-08.

> "discrete-time hazard model · survival gradient boosting · P(stop_hit|t)
>  · P(reversal|t) · P(+1R before -1R) · P(+2R before -1R) ·
>  time-to-reversal · Compare against simple baselines."

WHY PATHS HAD TO BE RECONSTRUCTED
----------------------------------
The cohort stores only path EXTREMES - `mae_pct`, `mfe_pct` and a
`stop_hit_within_20d` boolean. A hazard model needs event TIMING: not
"was the stop hit" but "on which day". So the daily path is rebuilt from
the price bars for each position, forward from its prediction date.

Reconstruction is PIT-safe in the sense that matters here: entry and stop
are fixed at the prediction date and never revised, and the forward walk
is the outcome being measured, not a feature. No forward information is
fed back into any predictor.

THE UNIT OF INDEPENDENCE IS THE EPISODE, NOT THE ROW
-----------------------------------------------------
This is the one place the standard effective-sample gate would be wrong
if applied unchanged. For classification, overlapping 10-day windows on
the same ticker are near-duplicates. For time-to-event, the unit is an
ENTRY EPISODE - one (ticker, entry_date) with its own stop and its own
path. Two episodes on the same ticker a month apart are two events.

So the gate here counts distinct episodes, and it is stated explicitly
rather than inherited silently. It is still a refusal gate: no threshold
cheating, and a market that cannot support the model does not get one.

R-MULTIPLES ANCHOR EVERYTHING
------------------------------
R = (entry - stop) / entry, the risk actually taken. +1R and +2R are
measured in that unit, so a 3% move on a 1.5%-risk position and on a
6%-risk position are not confused with each other.

RESEARCH ONLY · reads price bars and the cohort, writes one report.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.exit_hazard.v1"
FAMILY = "R3G_EXIT_HAZARD_V1"

MAX_DAYS = 20
REVERSAL_GIVEBACK = 0.5      # gave back half of peak favourable excursion
MIN_EPISODES = 50            # engineering gate · episodes, not rows


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


def _series(root: Path, market: str, ticker: str):
    from backend.research.ml_discovery.temporal import _load_series
    return _load_series(root, market, ticker)


def walk(dates, closes, entry_date: date, entry: float, stop: float,
         max_days: int = MAX_DAYS) -> Optional[dict]:
    """Rebuild the daily path and time every event on it."""
    R = (entry - stop) / entry * 100.0
    if R <= 0:
        return None
    start = None
    for i, d in enumerate(dates):
        if d > entry_date:
            start = i
            break
    if start is None:
        return None
    path = closes[start:start + max_days]
    if len(path) < 2:
        return None

    day_stop = day_1r = day_2r = None
    peak_r, peak_day = 0.0, 0
    trough_r = 0.0
    day_reversal = None
    for k, px in enumerate(path, start=1):
        r = (px / entry - 1.0) * 100.0 / R      # return in R units
        if r > peak_r:
            peak_r, peak_day = r, k
        if r < trough_r:
            trough_r = r
        if day_stop is None and r <= -1.0:
            day_stop = k
        if day_1r is None and r >= 1.0:
            day_1r = k
        if day_2r is None and r >= 2.0:
            day_2r = k
        # Reversal · peaked at >= +1R then gave back half of that peak.
        if (day_reversal is None and peak_r >= 1.0
                and r <= peak_r * REVERSAL_GIVEBACK):
            day_reversal = k

    final_r = (path[-1] / entry - 1.0) * 100.0 / R
    return {
        "R_pct": round(R, 4),
        "n_days_observed": len(path),
        "day_stop_hit": day_stop,
        "day_first_1R": day_1r,
        "day_first_2R": day_2r,
        "day_reversal": day_reversal,
        "peak_r": round(peak_r, 4), "peak_day": peak_day,
        "trough_r": round(trough_r, 4),
        "final_r": round(final_r, 4),
        # Race outcomes · which came first, the target or the stop.
        "hit_1R_before_stop": (day_1r is not None
                               and (day_stop is None or day_1r < day_stop)),
        "hit_2R_before_stop": (day_2r is not None
                               and (day_stop is None or day_2r < day_stop)),
        "stop_hit": day_stop is not None,
        "reversed": day_reversal is not None,
    }


def build_episodes(root: Path, market: str, rows: list) -> list:
    """One episode per (ticker, prediction_date) that has a real stop."""
    seen, out, cache = set(), [], {}
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        d = _d(r.get("prediction_date"))
        entry, stop = _num(r.get("entry_price_at_pred")), _num(r.get("stop_at_pred"))
        if not t or d is None or entry is None or stop is None:
            continue
        key = (t, d)
        if key in seen:
            continue
        seen.add(key)
        if t not in cache:
            cache[t] = _series(root, market, t)
        s = cache[t]
        if s is None:
            continue
        w = walk(s[0], s[1], d, entry, stop)
        if w is None:
            continue
        out.append({
            "ticker": t, "entry_date": d.isoformat(),
            "confidence_pct": _num(r.get("confidence_pct")),
            "vol_20d_pct": _num(r.get("vol_20d_pct")),
            "ma200_dist_pct": _num(r.get("ma200_dist_pct")),
            "momentum_20d_pct": _num(r.get("momentum_20d_pct")),
            "rank": _num(r.get("rank")),
            "stop_distance_pct": round((entry - stop) / entry * 100, 4),
            **w,
        })
    return out


def discrete_hazard(eps: list, event_key: str) -> list:
    """P(event on day k | survived to k-1) · the classical life-table."""
    out, at_risk = [], len(eps)
    alive = list(eps)
    for k in range(1, MAX_DAYS + 1):
        if not alive:
            break
        events = [e for e in alive if e.get(event_key) == k]
        censored = [e for e in alive if e["n_days_observed"] < k
                    and e.get(event_key) is None]
        h = len(events) / len(alive) if alive else 0.0
        out.append({
            "day": k, "at_risk": len(alive), "events": len(events),
            "hazard_pct": round(h * 100, 2),
            "cumulative_event_pct": round(
                (1 - math.prod(1 - x["hazard_pct"] / 100 for x in out)
                 * (1 - h)) * 100, 2),
        })
        alive = [e for e in alive
                 if e.get(event_key) != k and e not in censored]
    return out


def _auc(y: list, p: list) -> Optional[float]:
    pos = [i for i, v in enumerate(y) if v == 1]
    neg = [i for i, v in enumerate(y) if v == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(p)), key=lambda i: p[i])
    rank = [0.0] * len(p)
    for r, i in enumerate(order, 1):
        rank[i] = r
    s = sum(rank[i] for i in pos)
    return round((s - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)), 4)


def model_vs_baselines(eps: list, target_key: str) -> dict:
    """Gradient-boosted survival-style classifier vs the obvious baselines.

    > "Compare against simple baselines."
    A model that cannot beat "wider stops survive longer" is not evidence.
    """
    import numpy as np
    feats = ["confidence_pct", "vol_20d_pct", "ma200_dist_pct",
             "momentum_20d_pct", "rank", "stop_distance_pct"]
    X, y = [], []
    for e in eps:
        vals = [e.get(f) for f in feats]
        if e.get(target_key) is None:
            continue
        X.append([float(v) if v is not None else float("nan") for v in vals])
        y.append(1 if e[target_key] else 0)
    if len(y) < 40 or len(set(y)) < 2:
        return {"error": "insufficient or single-class target"}
    X, y = np.array(X, dtype=float), np.array(y, dtype=int)

    # Ticker-disjoint folds · a name must never be in train and test.
    tick = [e["ticker"] for e in eps if e.get(target_key) is not None]
    uniq = sorted(set(tick))
    assign = {t: i % 5 for i, t in enumerate(uniq)}
    folds = []
    for k in range(5):
        tr = [i for i, t in enumerate(tick) if assign[t] != k]
        te = [i for i, t in enumerate(tick) if assign[t] == k]
        if len(tr) > 20 and len(te) > 5 and len(set(y[tr])) == 2:
            folds.append((tr, te))
    if not folds:
        return {"error": "no usable ticker-disjoint folds"}

    import lightgbm as lgb
    aucs, base_stop, base_vol, imps = [], [], [], []
    for tr, te in folds:
        m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                               learning_rate=0.05, n_estimators=200,
                               min_child_samples=15, reg_lambda=1.0,
                               verbose=-1, random_state=20260908)
        m.fit(X[tr], y[tr])
        aucs.append(_auc(list(y[te]), list(m.predict_proba(X[te])[:, 1])))
        # Baseline 1 · a wider stop is simply harder to hit.
        base_stop.append(_auc(list(y[te]),
                              [-X[i][feats.index("stop_distance_pct")]
                               for i in te]))
        # Baseline 2 · more volatile names hit stops more often.
        base_vol.append(_auc(list(y[te]),
                             [X[i][feats.index("vol_20d_pct")] for i in te]))
        tot = float(sum(m.feature_importances_)) or 1.0
        imps.append({f: round(float(v) / tot, 4)
                     for f, v in zip(feats, m.feature_importances_)})
    mean_imp = {f: round(sum(d[f] for d in imps) / len(imps), 4) for f in feats}
    ok = [a for a in aucs if a is not None]
    bs = [a for a in base_stop if a is not None]
    bv = [a for a in base_vol if a is not None]
    return {
        "n_episodes": len(y), "event_rate_pct": round(y.mean() * 100, 1),
        "n_folds": len(folds),
        "model_auc_folds": aucs,
        "model_auc_mean": round(sum(ok) / len(ok), 4) if ok else None,
        "baseline_stop_distance_auc_mean": (round(sum(bs) / len(bs), 4)
                                            if bs else None),
        "baseline_volatility_auc_mean": (round(sum(bv) / len(bv), 4)
                                         if bv else None),
        "beats_best_baseline": (
            bool(ok and (bs or bv)
                 and sum(ok) / len(ok) > max(
                     sum(bs) / len(bs) if bs else 0,
                     sum(bv) / len(bv) if bv else 0))),
        "feature_importance_mean": dict(
            sorted(mean_imp.items(), key=lambda kv: -kv[1])),
    }


def analyse(root: Path, market: str) -> dict:
    from backend.research.cohort.entry_backfill import backfill
    from backend.research.cohort.mr_dependency_v1 import load_cohort

    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}
    backfill(root, market, rows)
    eps = build_episodes(root, market, rows)

    tick = Counter(e["ticker"] for e in eps)
    gate_ok = len(eps) >= MIN_EPISODES
    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · no production rule · R2 stop unchanged",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_episodes": len(eps),
        "n_tickers": len(tick),
        "episodes_per_ticker": round(len(eps) / max(1, len(tick)), 2),
        "gate": {
            "unit": "ENTRY EPISODE (ticker, entry_date) with a real stop",
            "min_episodes": MIN_EPISODES,
            "passes": gate_ok,
            "rationale": (
                "For time-to-event the unit of independence is the episode, "
                "not the daily row · two episodes on one ticker a month "
                "apart are two events. Stated explicitly rather than "
                "inheriting the classification gate silently."),
        },
    }
    if not gate_ok:
        rep["refusal"] = (
            "NO HAZARD MODEL FITTED · %d episodes < %d"
            % (len(eps), MIN_EPISODES))
        return rep

    rep["outcomes"] = {
        "stop_hit_pct": round(sum(1 for e in eps if e["stop_hit"])
                              / len(eps) * 100, 1),
        "reached_1R_pct": round(sum(1 for e in eps if e["day_first_1R"])
                                / len(eps) * 100, 1),
        "reached_2R_pct": round(sum(1 for e in eps if e["day_first_2R"])
                                / len(eps) * 100, 1),
        "reversed_pct": round(sum(1 for e in eps if e["reversed"])
                              / len(eps) * 100, 1),
        "P_1R_before_stop_pct": round(
            sum(1 for e in eps if e["hit_1R_before_stop"]) / len(eps) * 100, 1),
        "P_2R_before_stop_pct": round(
            sum(1 for e in eps if e["hit_2R_before_stop"]) / len(eps) * 100, 1),
        "median_day_stop_hit": _median([e["day_stop_hit"] for e in eps
                                        if e["day_stop_hit"]]),
        "median_day_first_1R": _median([e["day_first_1R"] for e in eps
                                        if e["day_first_1R"]]),
        "median_day_reversal": _median([e["day_reversal"] for e in eps
                                        if e["day_reversal"]]),
        "mean_peak_r": round(sum(e["peak_r"] for e in eps) / len(eps), 3),
        "mean_final_r": round(sum(e["final_r"] for e in eps) / len(eps), 3),
    }
    rep["hazard_stop_hit"] = discrete_hazard(eps, "day_stop_hit")
    rep["hazard_reversal"] = discrete_hazard(eps, "day_reversal")
    rep["hazard_first_1R"] = discrete_hazard(eps, "day_first_1R")
    rep["models"] = {
        "stop_hit": model_vs_baselines(eps, "stop_hit"),
        "hit_1R_before_stop": model_vs_baselines(eps, "hit_1R_before_stop"),
        "reversed": model_vs_baselines(eps, "reversed"),
    }
    return rep


def _median(v: list):
    v = sorted(x for x in v if x is not None)
    return v[len(v) // 2] if v else None


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "cohort"
         / f"exit_hazard_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "cohort"
         / f"exit_hazard_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3-G exit hazard research")
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
        print(f"exit_hazard:{m} · episodes {rep['n_episodes']} · tickers "
              f"{rep['n_tickers']} · gate {'PASS' if rep['gate']['passes'] else 'REFUSE'}")
        if rep.get("refusal"):
            print(f"    {rep['refusal']}")
        else:
            o = rep["outcomes"]
            print(f"    stop-hit {o['stop_hit_pct']}% · 1R-before-stop "
                  f"{o['P_1R_before_stop_pct']}% · reversed {o['reversed_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
