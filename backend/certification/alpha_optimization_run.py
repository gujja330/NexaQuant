"""Runner for the 3 alpha-optimization measurements (Article 101.2)."""
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

    # 1. Alpha Optimization
    from backend.certification.alpha_optimization import run_alpha_optimization
    ao = run_alpha_optimization(_ROOT)
    (reports / "alpha_optimization_report.json").write_text(
        json.dumps(ao, indent=2, default=str), encoding="utf-8")
    print(f"[alpha_optimization] n_trades={ao.get('n_trades')} "
          f"n_dims={len(ao.get('dimension_analysis',{}))} "
          f"n_interactions={len(ao.get('interaction_effects',{}))} "
          f"top_generator={ao.get('top_alpha_generators',[{}])[0].get('sector','n/a')} "
          f"top_destroyer={ao.get('top_alpha_destroyers',[{}])[0].get('sector','n/a')}")

    # 2. Confidence Scale Adapter
    from backend.certification.confidence_scale_adapter import (
        fit_scale_map, apply_scale_adapter_to_recs,
    )
    lp = _ROOT / "reports" / "learning.parquet"
    if lp.exists():
        df = pd.read_parquet(lp)
        smap = fit_scale_map(df["confidence"])
        smap_dict = asdict(smap)
        (reports / "confidence_scale_map.json").write_text(
            json.dumps(smap_dict, indent=2, default=str), encoding="utf-8")
        # Enrich recs
        rp = reports / "recommendations.json"
        if rp.exists():
            payload = json.loads(rp.read_text(encoding="utf-8"))
            enriched = apply_scale_adapter_to_recs(payload.get("recommendations", []), smap_dict)
            payload["recommendations"] = enriched
            payload["scale_adapter_source"] = smap_dict["engine"]
            rp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"[scale_adapter] n_historical={smap.n_historical} "
              f"P05={smap.historical_p05} P95={smap.historical_p95} "
              f"(recs enriched with aligned_confidence)")

    # 3. DNA Outcome Backfill
    from backend.certification.dna_outcome_backfill import run_backfill
    bf = run_backfill(_ROOT)
    (reports / "dna_outcome_backfill.json").write_text(
        json.dumps(asdict(bf), indent=2, default=str), encoding="utf-8")
    print(f"[dna_backfill] n_dna={bf.n_dna_records} n_learning={bf.n_learning_trades} "
          f"matched={bf.n_matched} rate={bf.match_rate_pct}% "
          f"-> {(reports/'dna_outcome_backfill.json').name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
