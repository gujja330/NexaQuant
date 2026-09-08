"""ML DISCOVERY v1 · RUNNER · CEO 2026-09-08.

Orchestrates: manifest -> effective-sample gate -> split choice -> fit ->
importance + stability -> interactions -> hypothesis ledger.

THE RUNNER'S JOB IS TO REFUSE
-----------------------------
> "The runner must refuse rather than silently downgrade the methodology."

Three honest outcomes, and the runner must land on exactly one:

  INSUFFICIENT_SUBSTRATE      no model is fitted at all
  CROSS_SECTIONAL_HYPOTHESIS  ticker-grouped folds only · says nothing
                              about persistence through time
  TIME_VALIDATED              walk-forward with embargo · the only result
                              eligible for the normal evidence pipeline

On today's cohort that means India refuses (37 effective units against a
minimum of 50) and USA runs cross-sectionally (495 units, but 7 prediction
dates cannot build an embargoed fold). Those are the correct answers, not
failures of the runner.

EXTENSION POINTS · deliberately left open, deliberately not built:
    sequence models (TCN / LSTM / Transformer)
    document/RAG-derived event features
    graph / KG features
    exit-policy RL
Each needs substrate this cohort does not have. The architecture admits
them; the runner does not pretend they are ready.

WRITES NOTHING TO PRODUCTION. No engine, no registry, no threshold.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.runner.v1"
FAMILY = "MLDISC_V1"
HORIZON = "fwd_10d_pct"

EXTENSION_POINTS = [
    "sequence_models · TCN/LSTM/Transformer · needs daily depth this "
    "cohort lacks",
    "document_rag_features · PIT document store required before any "
    "retrieval output may become a predictive feature",
    "graph_kg_features · historical community substrate missing",
    "exit_policy_rl · needs a stable environment, reward and execution "
    "simulator",
]


def run_market(root: Path, market: str) -> dict:
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.ml_discovery import (
        effective_sample as es, importance as imp, interactions as inter,
        ledger, manifest, models, splits)

    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}
    pop = [r for r in rows if r.get(HORIZON) is not None]

    # TEMPORAL LAYER · lags, rolling windows, multi-horizon targets.
    # Attached BEFORE the manifest so the coverage report covers them too.
    # Every temporal feature is PIT-safe by construction: price-derived
    # ones read only bars dated <= the prediction date, cohort-derived
    # ones only prior observations. Columns below the coverage floor are
    # DROPPED, not emitted as mostly-NaN - USA loses every model-feature
    # lag beyond t-1 that way, which is the correct outcome for a cohort
    # with 2.2 observations per ticker.
    from backend.research.ml_discovery import temporal
    temporal_cov = temporal.attach(root, market, pop)
    horizons = temporal.horizon_targets(pop)

    man = manifest.build(pop, market)
    manifest.emit(root, man)
    feats = [f["feature"] for f in man["features"] if f["fittable"]]
    feats += [f for f in temporal_cov["usable_features"] if f not in feats]

    gate = es.assess(pop, horizon_days=es.FORWARD_HORIZON)
    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "market": market.lower(),
        "horizon": HORIZON,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": len(pop),
        "verdict": gate["verdict"],
        "readiness": gate,
        "manifest_summary": {
            "n_fittable": man["n_fittable"], "n_excluded": man["n_excluded"],
            "excluded_by_reason": man["excluded_by_reason"],
            "fittable_features": feats,
        },
        "production_impact": "NONE",
        "temporal": {
            "n_generated": temporal_cov["n_generated"],
            "n_usable": temporal_cov["n_usable"],
            "n_dropped_low_coverage": temporal_cov["n_dropped_low_coverage"],
            "dropped": temporal_cov["dropped"],
            "min_coverage_pct": temporal_cov["min_coverage_pct"],
            "lags": temporal.LAGS,
            "rolling_windows": temporal.ROLL_WINDOWS,
        },
        "horizons": horizons,
        "extension_points": EXTENSION_POINTS,
    }

    if not gate["may_fit"]:
        rep["fit"] = None
        rep["refusal"] = (
            "NO MODEL FITTED. " + " · ".join(gate["blocking_reasons"]))
        return rep

    # Split strategy follows the verdict · never the other way round.
    if gate["time_validated"]:
        folds = splits.walk_forward(pop, n_folds=es.MIN_WALK_FORWARD_FOLDS,
                                    embargo_days=es.EMBARGO_DAYS)
        kind = splits.WALK_FORWARD
    else:
        folds = splits.grouped_by_ticker(pop, n_folds=5)
        kind = splits.GROUPED_TICKER
    if not folds:
        rep["fit"] = None
        rep["refusal"] = "NO MODEL FITTED · no usable folds for %s" % kind
        return rep

    fits = {}
    for target in (models.TARGET_RETURN, models.TARGET_WINNER,
                   models.TARGET_SEVERE_LOSS):
        X, y, names, _ = models.build_matrix(pop, feats, target, HORIZON)
        if X is None or X.shape[0] < 30 or len(names) < 3:
            continue
        per_fold_perm, per_fold_native, scores = [], [], []
        for tr, te in folds:
            if len(tr) < 20 or len(te) < 10:
                continue
            if target != models.TARGET_RETURN and len(set(y[tr])) < 2:
                continue
            m = models.fit(X[tr], y[tr], target)
            scores.append(models.score(m, X[te], y[te], target))
            per_fold_native.append(imp.native(m, names))
            per_fold_perm.append(
                imp.permutation(m, X[te], y[te], names, target))
        if not per_fold_perm:
            continue
        stab = imp.stability(per_fold_perm, names)
        fits[target] = {
            "split": kind,
            "split_meaning": splits.describe(kind),
            "n_folds_used": len(per_fold_perm),
            "held_out_scores": scores,
            "permutation_stability": stab,
            "native_importance_last_fold": per_fold_native[-1],
            "candidates": imp.candidates(stab),
        }
    rep["fit"] = fits

    # Interactions · only on the features that proved stable somewhere.
    stable = sorted({c["feature"] for f in fits.values()
                     for c in f["candidates"]})
    rep["interaction_scan"] = (
        inter.scan(pop, stable or feats, HORIZON) if len(stable or feats) >= 2
        else [])

    # Register · one entry per stable candidate, never a rule.
    registered = []
    for target, f in fits.items():
        for c in f["candidates"]:
            r = ledger.register(
                root, market, f"importance:{target}", [c["feature"]],
                gate["verdict"],
                {"mean_rank": c["mean_rank"],
                 "rank_spread_frac": c["rank_spread_frac"],
                 "top_quartile_hits": c["top_quartile_hits"],
                 "n_folds": c["n_folds"], "split": f["split"]},
                HORIZON)
            if r:
                registered.append(r["hypothesis_id"])
    for it in (rep["interaction_scan"] or [])[:3]:
        r = ledger.register(
            root, market, "interaction", [it["feature_a"], it["feature_b"]],
            gate["verdict"],
            {"interaction_strength_pp": it["interaction_strength_pp"],
             "min_cell_tickers": it["min_cell_tickers"]}, HORIZON)
        if r:
            registered.append(r["hypothesis_id"])
    rep["hypotheses_registered"] = registered
    return rep


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"readiness_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"readiness_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="ML Discovery v1 runner")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run_market(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        emit(root, rep)
        g = rep["readiness"]["measurement"]
        print(f"mldisc:{m} · {rep['verdict']} · rows {g['n_rows']} · "
              f"tickers {g['n_unique_tickers']} · dates "
              f"{g['n_prediction_dates']} · effective {g['effective_units']}")
        if rep.get("refusal"):
            print(f"    {rep['refusal']}")
        else:
            print(f"    fitted targets: {list((rep.get('fit') or {}).keys())} "
                  f"· hypotheses registered: "
                  f"{len(rep.get('hypotheses_registered') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
