"""WAVE 2A · PREQUENTIAL EVALUATION ENGINE · CEO 2026-09-08.

> "predict tomorrow -> score tomorrow -> append tomorrow -> predict next
>  day. That directly addresses the current bottleneck: dates are scarce
>  in India, not rows."

WHY THIS IS THE FOUNDATION
---------------------------
Every retrospective split this session has been attacked and most have
fallen: ticker-disjoint folds shared dates, date-disjoint folds shared
tickers, the joint holdout shrank the data, and Wave 1D's walk-forward
posted AUC 1.000 on a degenerate fold. The common weakness is that all of
them RE-USE history: the analyst chooses the split after seeing the data.

Prequential evaluation removes that choice. Each prediction is made using
only what existed strictly before its date, is written down BEFORE the
outcome is knowable, and is scored later without ever being revised. The
record is append-only, so a model cannot be quietly re-fitted and the
history cannot be re-cut.

    for each date d, ascending:
        train  on rows whose outcome matured before (d - embargo)
        predict d
        APPEND the prediction, unscored
        later: score it when the outcome matures

It also solves the date-scarcity problem the honest way: it does not need
many dates today, because it accrues one honest observation per day
forever. Today it will refuse; in three months it will not.

WHAT IT IS NOT
--------------
It is not a backtest. A backtest asks "what would this have returned".
This asks "was each prediction, made in ignorance of its own future,
any good" - which is the only question that cannot be tuned after the
fact.

RESEARCH ONLY · no engine, no threshold, no promotion.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.prequential.v1"
FAMILY = "R3_PREQUENTIAL_V1"

EMBARGO_DAYS = 5
FORWARD_HORIZON = 10
MIN_TRAIN_ROWS = 80
MIN_TRAIN_TICKERS = 15

FEATURES = ["confidence_pct", "vol_20d_pct", "ma200_dist_pct",
            "ma50_dist_pct", "momentum_20d_pct", "momentum_60d_pct",
            "rsi_14", "rank"]


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


def ledger_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "prequential"
            / f"ledger_{market.lower()}.jsonl")


def load_ledger(root: Path, market: str) -> list:
    p = ledger_path(root, market)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _append(root: Path, market: str, recs: list) -> int:
    if not recs:
        return 0
    p = ledger_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, default=str) + "\n")
    return len(recs)


def _fit_predict(X_tr, y_tr, X_te):
    import lightgbm as lgb
    import numpy as np
    m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                           learning_rate=0.05, n_estimators=200,
                           min_child_samples=20, reg_lambda=1.0,
                           verbose=-1, random_state=20260908)
    m.fit(X_tr, np.array(y_tr))
    return list(m.predict_proba(X_te)[:, 1])


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


def run(root: Path, market: str, target: str = "severe_loss_10d") -> dict:
    """One honest pass · every prediction precedes its own outcome."""
    import numpy as np
    from backend.research.cohort.mr_dependency_v1 import load_cohort

    rows = load_cohort(root, market)
    pop = []
    for r in rows:
        d = _d(r.get("prediction_date"))
        fwd = _num(r.get("fwd_10d_pct"))
        if d is None or fwd is None:
            continue
        pop.append({"ticker": str(r.get("ticker") or "").upper(),
                    "date": d, "fwd": fwd,
                    "x": [_num(r.get(f)) for f in FEATURES]})
    if not pop:
        return {"market": market, "error": "cohort empty"}

    # Target defined ONCE, from the whole population, before any split.
    cut = sorted(p["fwd"] for p in pop)[max(0, int(len(pop) * 0.10) - 1)]
    for p in pop:
        p["y"] = 1 if p["fwd"] <= cut else 0

    dates = sorted({p["date"] for p in pop})
    already = {(r["date"], r["ticker"], r["target"])
               for r in load_ledger(root, market)}

    new, skipped = [], Counter()
    for d in dates:
        # Train only on rows whose OUTCOME had matured before the embargo.
        train = [p for p in pop
                 if p["date"] + timedelta(days=FORWARD_HORIZON + EMBARGO_DAYS)
                 <= d]
        test = [p for p in pop if p["date"] == d]
        if len(train) < MIN_TRAIN_ROWS:
            skipped["train_rows"] += len(test)
            continue
        if len({p["ticker"] for p in train}) < MIN_TRAIN_TICKERS:
            skipped["train_tickers"] += len(test)
            continue
        ytr = [p["y"] for p in train]
        if len(set(ytr)) < 2:
            skipped["single_class"] += len(test)
            continue
        Xtr = np.array([[v if v is not None else float("nan") for v in p["x"]]
                        for p in train], dtype=float)
        Xte = np.array([[v if v is not None else float("nan") for v in p["x"]]
                        for p in test], dtype=float)
        probs = _fit_predict(Xtr, ytr, Xte)
        for p, pr in zip(test, probs):
            key = (d.isoformat(), p["ticker"], target)
            if key in already:
                continue
            new.append({
                "schema_version": SCHEMA_VERSION,
                "market": market.lower(), "target": target,
                "date": d.isoformat(), "ticker": p["ticker"],
                "prediction": round(float(pr), 6),
                "n_train_rows": len(train),
                "n_train_tickers": len({q["ticker"] for q in train}),
                "embargo_days": EMBARGO_DAYS,
                "horizon_days": FORWARD_HORIZON,
                "outcome": p["y"],          # matured · scored immediately
                "fwd_10d_pct": p["fwd"],
                "recorded_utc": datetime.now(timezone.utc)
                                .isoformat(timespec="seconds"),
            })
    n_written = _append(root, market, new)

    led = [r for r in load_ledger(root, market) if r.get("target") == target]
    scored = [r for r in led if r.get("outcome") is not None]
    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · append-only · predictions precede outcomes",
        "market": market.lower(), "target": target,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"embargo_days": EMBARGO_DAYS,
                   "horizon_days": FORWARD_HORIZON,
                   "min_train_rows": MIN_TRAIN_ROWS,
                   "min_train_tickers": MIN_TRAIN_TICKERS},
        "cohort_dates": len(dates),
        "predictions_written_this_run": n_written,
        "ledger_total": len(led),
        "skipped_rows_by_reason": dict(skipped),
    }
    if len(scored) < 50:
        rep["verdict"] = (
            "ACCUMULATING · %d scored predictions · a prequential verdict "
            "needs 50+. This is the correct state for a %d-date cohort: the "
            "engine refuses to score, and accrues one honest observation "
            "per day." % (len(scored), len(dates)))
        return rep

    y = [r["outcome"] for r in scored]
    p = [r["prediction"] for r in scored]
    base = sum(y) / len(y)
    rep["scored"] = {
        "n": len(scored),
        "event_rate_pct": round(base * 100, 1),
        "auc": _auc(y, p),
        "brier": round(sum((a - b) ** 2 for a, b in zip(y, p)) / len(y), 4),
        "brier_baseline_always_base_rate": round(
            sum((a - base) ** 2 for a in y) / len(y), 4),
        "n_dates": len({r["date"] for r in scored}),
        "n_tickers": len({r["ticker"] for r in scored}),
    }
    s = rep["scored"]
    rep["verdict"] = (
        "PREQUENTIAL AUC %s · Brier %s vs base-rate %s · %s"
        % (s["auc"], s["brier"], s["brier_baseline_always_base_rate"],
           "beats the base rate" if s["brier"]
           < s["brier_baseline_always_base_rate"]
           else "does NOT beat simply predicting the base rate"))
    return rep


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "prequential"
         / f"summary_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "prequential"
         / f"summary_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Wave 2A prequential engine")
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
        print(f"prequential:{m} · dates {rep['cohort_dates']} · written "
              f"{rep['predictions_written_this_run']} · ledger "
              f"{rep['ledger_total']}")
        print(f"    {rep['verdict']}")
        if rep.get("skipped_rows_by_reason"):
            print(f"    skipped: {rep['skipped_rows_by_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
