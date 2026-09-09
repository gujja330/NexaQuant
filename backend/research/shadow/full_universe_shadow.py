"""AEGIS · FULL-UNIVERSE SHADOW RECOMMENDATION PATH · CEO 2026-09-08.

> "Create a shadow full-universe recommendation path using all scored names
>  and record: how many clear 0.55 confidence, how many survive
>  disagreement, how many survive regime floor, how many would become NEW,
>  which tickers they are, why each rejected candidate fails. This gives us
>  the evidence before touching R2 production."

THE DEFECT THIS MEASURES
------------------------
`india/model_factory/run.py` scores the FULL universe and then persists a
truncated view::

    "top_10":   [... ens.predictions.head(10) ...]
    "bottom_5": [... ens.predictions.tail(5)  ...]

`model_metrics.json` proves the work is done - `n_scored` is 228 (India)
and 516 (USA) for all 11 models. But `ensemble.json` keeps 15 rows, and
`recommendation_intelligence/run.py:79` reads exactly those::

    ens_rows = list(ens.get("top_10", [])) + list(ens.get("bottom_5", []))

So R2 has been choosing from 15 names out of 228. Roughly 97% of a
completed evaluation is discarded at a persistence boundary - not at a
compute limit, and not by any threshold.

WHAT THIS MODULE DOES *NOT* DO
------------------------------
It changes NOTHING in production. It does not widen R2, does not touch a
threshold, does not write `ensemble.json`, `recommendations_v3.json`, the
registry, or any model-registry entry. Its single output is

    reports/research/shadow/full_universe_shadow_{market}.json

The confidence floor stays at the published 0.55 and the regime floor at
0.55. The only variable changed is HOW MANY NAMES ARE OFFERED to the
unchanged engine - which is precisely the question the evidence has to
answer before anyone removes the truncation.

METHOD
------
The shadow deliberately re-runs the SAME code path rather than
reimplementing it - `ModelFactory.predict_all` then `ensemble_predict`
then `RecommendationEngine.run` - so any difference in the result is
attributable to breadth alone and not to a second implementation drifting
from the first.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.shadow.full_universe.v1"

# Published R2 defaults · MIRRORED, never redefined here. If production
# ever moves these the shadow must move with it or the comparison lies.
CONF_FLOOR = 0.55
REGIME_CONF_FLOOR = 0.55

MARKETS = {
    "india": {"reports": "reports",
              "weights": "configs/ensemble_weights_adaptive.yaml"},
    "usa": {"reports": "usa/reports",
            "weights": "usa/configs/ensemble_weights_adaptive.yaml"},
}

# Why a scored name never becomes NEW · ordered as the engine applies them,
# so the FIRST failing gate is the reason reported.
R_HOLD = "HOLD · engine produced no BUY/SELL action"
R_DISAGREE = "DISAGREEMENT · models conflict · collapsed to HOLD"
R_CONF = "CONFIDENCE · calibrated < %.2f" % CONF_FLOOR
R_REGIME = "REGIME · regime-adjusted < %.2f" % REGIME_CONF_FLOOR
R_NOT_BUY = "NOT A BUY · action is a SELL-family signal"
R_PASS = "PASS · would reach registry as a NEW candidate"

BUY_FAMILY = {"BUY", "STRONG_BUY", "STRONG BUY", "ACCUMULATE", "ADD"}


def _action(rec_or_str) -> str:
    """Normalise the engine's Action enum to a bare name.

    `action` is an enum, so `str(Action.HOLD)` is "ACTION.HOLD" - which
    compares unequal to "HOLD" and silently counts every HOLD as a signal.
    That inverted the first shadow run's non-HOLD count from 0 to 228.
    """
    v = rec_or_str if isinstance(rec_or_str, str) else getattr(
        rec_or_str, "action", "")
    v = getattr(v, "value", v)
    return str(v or "").split(".")[-1].upper().strip()


def _reports(root: Path, market: str) -> Path:
    return root / MARKETS[market]["reports"]


def _load_selected(root: Path, market: str) -> list:
    p = _reports(root, market) / "selected_features.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("selected", [])
    except Exception:
        return []


def _load_regime(root: Path, market: str) -> str:
    p = _reports(root, market) / "market_intelligence_summary.json"
    if not p.exists():
        return "unknown"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("regime", "unknown")
    except Exception:
        return "unknown"


def _persisted_ensemble_tickers(root: Path, market: str) -> set:
    """The names production actually OFFERS TO ELIGIBILITY.

    This used to read top_10 + bottom_5 only, because that was all
    ensemble.json persisted - and that was the defect, not the baseline.
    Four qualified USA candidates (COP, DVN, MPC, TRV) were discarded
    before any rule could judge them.

    `all_candidates` now carries the full universe, so it is preferred.
    The 15-row slice remains the fallback for an ensemble.json written by
    an older run, and when that fallback is used the caller can tell,
    because the set will be exactly 15 names wide.
    """
    p = _reports(root, market) / "ensemble.json"
    if not p.exists():
        return set()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return set()
    out = set()
    for r in d.get("all_candidates") or []:
        t = r.get("ticker")
        if t:
            out.add(str(t))
    if out:
        return out
    for key in ("top_10", "bottom_5"):
        for r in d.get(key) or []:
            t = r.get("ticker")
            if t:
                out.add(str(t))
    return out


def _classify(rec) -> str:
    """First gate a recommendation fails · gates in engine order."""
    action = _action(rec)
    if getattr(rec, "disagreement_flag", False):
        return R_DISAGREE
    if action in ("HOLD", ""):
        return R_HOLD
    if float(getattr(rec, "calibrated_confidence", 0.0) or 0.0) < CONF_FLOOR:
        return R_CONF
    if float(getattr(rec, "regime_adjusted_confidence", 0.0) or 0.0) < REGIME_CONF_FLOOR:
        return R_REGIME
    if action not in BUY_FAMILY:
        return R_NOT_BUY
    return R_PASS


def compute(root: Path, market: str) -> dict:
    """Score the FULL universe through the unchanged production engine."""
    import sys
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from backend.feature_store import schema_fingerprint
    from backend.feature_store.feature_history import list_snapshots, read_snapshot
    from backend.model_factory import (
        ModelFactory, EnsembleWeights, ensemble_predict)
    from backend.certification.adaptive_weights import load_ensemble_weights_config
    from backend.recommendation import RecommendationEngine

    m = market.lower()
    snaps = list_snapshots(root, m)
    if not snaps:
        return {"error": "no feature snapshot", "market": m}
    latest = snaps[-1]
    df = read_snapshot(root, m, latest)
    if df is None or df.empty:
        return {"error": "feature snapshot empty", "market": m}

    selected = _load_selected(root, m)
    identity = {"market", "ticker", "asof", "sector", "currency"}
    keep = (identity | set(selected) | {"return_20d_pct"}) & set(df.columns)
    df_sub = df[[c for c in df.columns if c in keep]] if selected else df

    # Identical to production: same factory, same weights, same ensemble.
    factory = ModelFactory(root, m)
    factory.train_all(df_sub, target=None, cutoff=latest)
    preds = factory.predict_all(df_sub, cutoff=latest)
    adaptive = load_ensemble_weights_config(root / MARKETS[m]["weights"])
    weights = (EnsembleWeights(weights=adaptive, strategy="adaptive_ic_weighted")
               if adaptive else None)
    ens = ensemble_predict(preds, weights=weights, market=m, asof=latest)

    # THE ONLY DIFFERENCE FROM PRODUCTION: every scored row is offered,
    # instead of head(10)+tail(5).
    all_rows = [
        {"ticker": str(r["ticker"]),
         "ensemble_score": float(r["ensemble_score"]),
         "ensemble_confidence": float(r["ensemble_confidence"]),
         "n_models_scoring": int(r["n_models_scoring"]),
         "per_model_score": r.get("per_model_score")}
        for _, r in ens.predictions.iterrows()
    ]

    engine = RecommendationEngine(
        repo_root=root, market=m, regime=_load_regime(root, m),
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
        # A shadow run must never register a model or reuse a production
        # stamp · this run is not a production decision.
        model_stamp={"model_id": "aegis.recommendation.v3",
                     "mode": "SHADOW_FULL_UNIVERSE"},
    )
    batch = engine.run(ensemble_top_rows=all_rows, features_df=df,
                       selected_features=selected, asof=latest)

    baseline = _persisted_ensemble_tickers(root, m)
    rows, by_reason = [], {}
    for rec in batch.recommendations:
        reason = _classify(rec)
        by_reason[reason] = by_reason.get(reason, 0) + 1
        t = str(getattr(rec, "ticker", ""))
        rows.append({
            "ticker": t,
            "action": _action(rec),
            "ensemble_score": getattr(rec, "ensemble_score", None),
            "calibrated_confidence": getattr(rec, "calibrated_confidence", None),
            "regime_adjusted_confidence": getattr(
                rec, "regime_adjusted_confidence", None),
            "disagreement_flag": bool(getattr(rec, "disagreement_flag", False)),
            "reason": reason,
            "would_be_new": reason == R_PASS,
            # Did production even get the chance to see this name today?
            "in_persisted_15": t in baseline,
        })

    passes = [r for r in rows if r["would_be_new"]]
    new_only_via_shadow = [r for r in passes if not r["in_persisted_15"]]

    funnel = {
        "F1_universe_scored": len(all_rows),
        "F2_persisted_to_production": len(baseline),
        "F3_recommendations_returned": len(rows),
        "F4_non_hold": sum(1 for r in rows
                           if _action(r["action"]) not in ("HOLD", "")),
        "F5_survived_disagreement": sum(
            1 for r in rows if not r["disagreement_flag"]
            and _action(r["action"]) not in ("HOLD", "")),
        "F6_survived_confidence_floor": sum(
            1 for r in rows if not r["disagreement_flag"]
            and _action(r["action"]) not in ("HOLD", "")
            and float(r["calibrated_confidence"] or 0.0) >= CONF_FLOOR),
        "F7_survived_regime_floor": sum(
            1 for r in rows if not r["disagreement_flag"]
            and _action(r["action"]) not in ("HOLD", "")
            and float(r["calibrated_confidence"] or 0.0) >= CONF_FLOOR
            and float(r["regime_adjusted_confidence"] or 0.0) >= REGIME_CONF_FLOOR),
        "F8_would_be_new": len(passes),
        "F9_would_be_new_missed_by_truncation": len(new_only_via_shadow),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "SHADOW · measurement only · zero production impact",
        "market": m,
        "asof": latest.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {"confidence_floor": CONF_FLOOR,
                       "regime_confidence_floor": REGIME_CONF_FLOOR,
                       "note": "unchanged from R2 production · not tuned here"},
        "funnel": funnel,
        "rejection_reasons": dict(sorted(by_reason.items(),
                                         key=lambda kv: -kv[1])),
        "would_be_new": sorted(
            passes, key=lambda r: -(r["ensemble_score"] or 0)),
        "would_be_new_missed_by_truncation": sorted(
            new_only_via_shadow, key=lambda r: -(r["ensemble_score"] or 0)),
        "rows": sorted(rows, key=lambda r: -(r["ensemble_score"] or 0)),
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "shadow"
            / f"full_universe_shadow_{market.lower()}.json")


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


def summary_line(rep: dict) -> str:
    f = rep.get("funnel") or {}
    return (f"shadow:{rep['market']} · scored {f.get('F1_universe_scored')} "
            f"(production sees {f.get('F2_persisted_to_production')}) · "
            f"non-HOLD {f.get('F4_non_hold')} · conf {f.get('F6_survived_confidence_floor')} "
            f"· regime {f.get('F7_survived_regime_floor')} · would-be NEW "
            f"{f.get('F8_would_be_new')} (missed by truncation "
            f"{f.get('F9_would_be_new_missed_by_truncation')})")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="AEGIS full-universe SHADOW recommendation path")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = compute(root, m)
        if rep.get("error"):
            print(f"shadow:{m} · ERROR · {rep['error']}")
            continue
        p = emit(root, rep)
        print(summary_line(rep))
        print(f"    -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
