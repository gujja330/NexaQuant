"""Runner for the 3 intelligence enhancements (Article 101.2 permitted).

  1. Confidence Calibration + Kelly (per-bucket win rate from real trades)
  2. Continuous Learning Effectiveness (per-dim IC + per-sector effectiveness)
  3. Regime → Strategy Router (regime maps to strategy weights)

All 3 consume EXISTING artifacts. NO new engines.
"""
from __future__ import annotations

import argparse, json, sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="india")
    args = ap.parse_args()
    reports = _ROOT / ("usa/reports" if args.market == "usa" else "reports")

    import pandas as pd

    # ── 1. Confidence Calibration ─────────────────────────────
    from backend.recommendation.quality.calibration import (
        fit_calibration_curve, apply_calibration_to_recs,
    )
    lp = _ROOT / "reports" / "learning.parquet"
    curve = None
    if lp.exists():
        df = pd.read_parquet(lp)
        curve_obj = fit_calibration_curve(df)
        curve = asdict(curve_obj)
        (reports / "recommendation_calibration_curve.json").write_text(
            json.dumps(curve, indent=2, default=str), encoding="utf-8")
        # Enrich current recs with calibrated Kelly
        rp = reports / "recommendations.json"
        if rp.exists():
            rec_payload = json.loads(rp.read_text(encoding="utf-8"))
            enriched = apply_calibration_to_recs(rec_payload.get("recommendations", []), curve)
            rec_payload["recommendations"] = enriched
            rec_payload["calibration_source"] = "learning.parquet@aegis.recommendation_quality.calibration.v1"
            rp.write_text(json.dumps(rec_payload, indent=2, default=str), encoding="utf-8")
        print(f"[calibration:{args.market}] fit {len(curve.get('buckets', []))} buckets · "
              f"n_trades={curve.get('n_total_trades')} · overall_kelly={curve.get('overall_kelly')} "
              f"-> recommendation_calibration_curve.json (+ enriched recs.json)")

    # ── 2. Continuous Learning Effectiveness ─────────────────
    from backend.certification.learning_effectiveness import compute_learning_effectiveness
    if lp.exists():
        df = pd.read_parquet(lp)
        rep = compute_learning_effectiveness(df)
        p = reports / "learning_effectiveness.json"
        p.write_text(json.dumps(asdict(rep), indent=2, default=str), encoding="utf-8")
        print(f"[learning_effectiveness] n_trades={rep.n_trades} "
              f"top_dims={[d['dimension'] for d in rep.top_predictive_dimensions[:3]]} "
              f"underperforming_sectors={[s['sector'] for s in rep.top_underperforming_sectors[:3]]} "
              f"-> {p.name}")

    # ── 3. Regime → Strategy Router ──────────────────────────
    from backend.macro_intel.regime_strategy_router import route_regime_to_strategies
    macro_p = reports / "macro_regime.json"
    vol_p = reports / "volatility_intelligence.json"
    regime = "unknown"; vol = ""; conf = None
    if macro_p.exists():
        md = json.loads(macro_p.read_text(encoding="utf-8"))
        regime = str(md.get("primary_regime", "unknown"))
        conf = md.get("confidence")
    if vol_p.exists():
        vd = json.loads(vol_p.read_text(encoding="utf-8"))
        vol = str(vd.get("regime", ""))
    decision = route_regime_to_strategies(regime, vol, conf,
                                            asof=date.today().isoformat(),
                                            market=args.market)
    p = reports / "regime_strategy_router.json"
    p.write_text(json.dumps(asdict(decision), indent=2, default=str), encoding="utf-8")
    print(f"[regime_strategy_router] regime={decision.regime} vol={decision.volatility_regime} "
          f"top={[s['strategy'] for s in decision.top_active_strategies]} -> {p.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
