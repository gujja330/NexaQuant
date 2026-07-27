"""Runner for institutional optimization: percentile-classifier + permutation
importance + adaptive weights."""
from __future__ import annotations

import argparse, json, sys
from dataclasses import asdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="india")
    args = ap.parse_args()
    reports = _ROOT / ("usa/reports" if args.market == "usa" else "reports")
    import pandas as pd

    # 1. Permutation Importance
    from backend.certification.permutation_importance import run_permutation_importance
    perm = run_permutation_importance(_ROOT, n_permutations=30)
    (reports / "permutation_importance.json").write_text(
        json.dumps(perm, indent=2, default=str), encoding="utf-8")
    top = perm.get("top_features_ranked", [])[:3]
    print(f"[permutation_importance] n_trades={perm.get('n_trades')} "
          f"top_predictive={[t['feature'] for t in top]}")

    # 2. Adaptive Weights (consumes alpha_optimization + permutation)
    from backend.certification.adaptive_weights import (
        compute_adaptive_weights, write_ensemble_weights_config,
    )
    ao_p = reports / "alpha_optimization_report.json"
    ao = json.loads(ao_p.read_text(encoding="utf-8")) if ao_p.exists() else {}
    aw = compute_adaptive_weights(ao)
    aw_p = reports / "adaptive_ensemble_weights.json"
    aw_p.write_text(json.dumps(asdict(aw), indent=2, default=str), encoding="utf-8")
    # Also write consumable config
    write_ensemble_weights_config(aw.adaptive_weights,
                                     _ROOT / "configs" / "ensemble_weights_adaptive.yaml")
    # Sort by delta for display
    top_boosted = sorted(aw.weight_change_pp.items(), key=lambda kv: -kv[1])[:3]
    top_reduced = sorted(aw.weight_change_pp.items(), key=lambda kv: kv[1])[:3]
    print(f"[adaptive_weights] baseline=1/{len(aw.baseline_weights)}={next(iter(aw.baseline_weights.values()))} "
          f"boosted={top_boosted} reduced={top_reduced}")

    # 3. Percentile-based classifier · apply to current SSoT recs
    from backend.recommendation.percentile_classifier import classify_by_percentile
    rp = reports / "recommendations.json"
    if rp.exists():
        payload = json.loads(rp.read_text(encoding="utf-8"))
        recs = payload.get("recommendations", [])
        rep = classify_by_percentile(recs)
        (reports / "percentile_classification.json").write_text(
            json.dumps(asdict(rep), indent=2, default=str), encoding="utf-8")
        # Enrich SSoT recs · add percentile_action field alongside existing action
        pct_by_ticker = {d["ticker"]: d for d in rep.decisions}
        for r in recs:
            pcd = pct_by_ticker.get(r["ticker"])
            if pcd:
                r["percentile_action"] = pcd["action"]
                r["score_percentile"] = pcd["score_percentile"]
                r["percentile_reason"] = pcd["reason"]
        payload["recommendations"] = recs
        payload["percentile_engine"] = "aegis.recommendation.percentile_classifier.v1"
        rp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"[percentile_classifier] n_recs={rep.n_recs} "
              f"action_distribution={rep.action_distribution}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
