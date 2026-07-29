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

        # Re-enrich investor-actionable fields · percentile_action was just
        # added, so investor_action/position_plan/why + rotation_intelligence
        # + lifecycle_state + evolution must be refreshed. Also rebuild
        # ceo_summary because the entry distribution + top opportunity
        # change after percentile classification.
        # CEO cycles 2-4 · investor-facing dual-decision + rotation + lifecycle + evolution + ceo summary.
        from backend.recommendation.investor_actionable import (
            enrich_batch, summarize_batch, build_ceo_summary,
        )
        from backend.recommendation.snapshot import (
            archive_snapshot, load_previous_snapshot,
        )
        from backend.recommendation.snapshot.store import snapshot_to_ticker_map

        # Load context artifacts if their engines have run today
        lifecycle_records = None
        dynamic_holding_decisions = None
        try:
            lp = reports / "recommendation_lifecycle.json"
            if lp.exists():
                lifecycle_records = (json.loads(lp.read_text(encoding="utf-8"))
                                        .get("records") or {})
            dhp = reports / "dynamic_holding.json"
            if dhp.exists():
                decisions = (json.loads(dhp.read_text(encoding="utf-8"))
                                .get("decisions") or [])
                dynamic_holding_decisions = {
                    str(d.get("ticker") or ""): d for d in decisions if d.get("ticker")
                }
        except Exception:
            pass

        # Cycle 4: previous snapshot for evolution deltas (post-percentile run)
        asof_str = payload.get("asof") or ""
        prev_snap = load_previous_snapshot(reports, args.market, asof_str) if asof_str else None
        previous_ticker_map = snapshot_to_ticker_map(prev_snap)

        enrich_batch(recs,
                        lifecycle_records=lifecycle_records,
                        dynamic_holding_decisions=dynamic_holding_decisions,
                        previous_ticker_map=previous_ticker_map,
                        asof=asof_str)
        payload["recommendations"] = recs
        payload["investor_actionable_engine"] = "aegis.recommendation.investor_actionable.v1"

        # v3.0 Option D: re-run Runner 1 validation after percentile (India-only).
        if args.market == "india":
            try:
                from backend.recommendation.validation_layer import build_validation_report
                from backend.recommendation.validation_layer.engine import enrich_recs_with_validation
                r1_csv = _ROOT / "data" / "aegis_today.csv"
                enrich_recs_with_validation(recs, r1_csv)
                v_report = build_validation_report(recs, r1_csv)
                payload["runner1_validation"] = {k: v for k, v in v_report.items()
                                                       if k != "per_rec_validation"}
                ac = v_report.get("agreement_counts", {})
                print(f"[runner1_validation:india] post-percentile consensus="
                      f"{v_report.get('consensus_pct')}% · agree={ac.get('AGREE', 0)} · "
                      f"disagree={ac.get('DISAGREE', 0)} · "
                      f"orphans={len(v_report.get('runner1_orphans', []))}")
            except Exception as _e:
                print(f"[runner1_validation:india] re-run failed · {type(_e).__name__}: {_e}")

        # Rebuild CEO summary with post-percentile distribution + LIVE regime.
        # v3.0 FINAL Phase 9 · never surface "unknown" · treat it as null-value
        # and fall back to the market_intelligence source.
        def _is_valid_regime(v):
            return v and str(v).strip().lower() not in ("unknown", "n/a", "none", "")
        try:
            regime = None
            mr_p = reports / "macro_regime.json"
            if mr_p.exists():
                mr_d = json.loads(mr_p.read_text(encoding="utf-8"))
                for k in ("primary_regime", "regime", "current_regime"):
                    v = mr_d.get(k)
                    if _is_valid_regime(v):
                        regime = v
                        break
            if not _is_valid_regime(regime):
                mi_p = reports / "market_intelligence.json"
                if mi_p.exists():
                    mi_d = json.loads(mi_p.read_text(encoding="utf-8"))
                    for k in ("regime", "current_regime"):
                        v = mi_d.get(k)
                        if _is_valid_regime(v):
                            regime = v
                            break
        except Exception:
            regime = None
        # Article 9: never display "unknown" · fall back to "not_available"
        # ONLY if truly no source resolved (should never happen in prod).
        ceo_summary = build_ceo_summary(recs, market=args.market,
                                             macro_regime=regime if _is_valid_regime(regime) else "not_available")
        payload["ceo_summary"] = ceo_summary

        summ = summarize_batch(recs)
        (reports / "investor_actionable_summary.json").write_text(
            json.dumps(summ, indent=2, ensure_ascii=False), encoding="utf-8")

        rp.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                        encoding="utf-8")

        # Cycle 4: re-archive today's snapshot so history reflects the
        # POST-percentile enrichment (idempotent for the same date).
        archive_snapshot(payload, reports, args.market, asof=asof_str or None)

        print(f"[percentile_classifier] n_recs={rep.n_recs} "
              f"action_distribution={rep.action_distribution}")
        print(f"[investor_actionable] entry_dist={summ['entry_decision_dist']} "
              f"if_holding_dist={summ['if_holding_decision_dist']} "
              f"actionable_entries={len(summ['actionable_entries'])} "
              f"actionable_exits={len(summ['actionable_exits'])} "
              f"rotations={summ.get('n_rotation_suggestions', 0)} "
              f"lifecycle_dist={summ.get('lifecycle_state_dist', {})}")
        print(f"[ceo_summary:{args.market}] {ceo_summary.get('recommended_action')} "
              f"| actionable={ceo_summary.get('actionable_count')} "
              f"| rotations={ceo_summary.get('rotations_count')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
