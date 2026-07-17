"""DEV019 publish — reports/industry_context.json + parquet mirror."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _asof_ist(asof_utc_iso: str) -> str:
    utc = datetime.fromisoformat(asof_utc_iso.replace("Z", "+00:00"))
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def build_bundle(compute_result: dict, code_sha: str = "nogit") -> dict:
    per_industry = compute_result.get("_per_industry", [])
    global_ctx = compute_result.get("_global_context")
    sector_ctx = compute_result.get("_sector_context")
    asof_iso = compute_result.get("asof_utc", _now_utc_iso())

    industries_out = []
    for entry in per_industry:
        if entry["status"] != "computed":
            industries_out.append({
                "industry_key": entry["industry_key"],
                "display_name": entry["display_name"],
                "parent_sector_key": entry.get("parent_sector_key"),
                "parent_sector_name": entry.get("parent_sector_name"),
                "status": entry["status"],
                "n_used": entry.get("n_used", 0),
                "n_defined": entry.get("n_defined", 0),
            })
            continue

        composite = entry["composite"]
        components = list(composite.component_indicators)
        sorted_c = sorted(components, key=lambda x: x["contribution_to_composite"], reverse=True)
        top_drivers = [{"indicator": c["indicator_key"],
                          "value_0_100": c["value_0_100"],
                          "weight": c["weight"],
                          "contribution": c["contribution_to_composite"]}
                         for c in sorted_c[:5]]
        detractors = sorted([c for c in components if c["value_0_100"] < 40],
                              key=lambda x: x["value_0_100"])[:3]

        industries_out.append({
            "industry_key": entry["industry_key"],
            "display_name": entry["display_name"],
            "parent_sector_key": entry["parent_sector_key"],
            "parent_sector_name": entry["parent_sector_name"],
            "status": "computed",
            "score": composite.value_0_100,
            "classification": composite.classification,
            "rotation": entry.get("rotation", "Unknown"),
            "confidence": composite.confidence,
            "leadership_rank": entry.get("leadership_rank"),
            "intra_sector_rank": entry.get("intra_sector_rank"),
            "intra_sector_total": entry.get("intra_sector_total"),
            "n_used": entry["n_used"],
            "n_defined": entry["n_defined"],
            "top_drivers": top_drivers,
            "top_detractors": [{"indicator": d["indicator_key"],
                                  "value_0_100": d["value_0_100"]} for d in detractors],
            "weighting_version": composite.weighting_version,
        })

    computed = [i for i in industries_out if i.get("status") == "computed"]
    non_computed = [i for i in industries_out if i.get("status") != "computed"]
    computed.sort(key=lambda x: x["score"], reverse=True)
    industries_final = computed + non_computed

    # Rotation aggregations
    rotation_dist: dict = {}
    for i in computed:
        rot = i.get("rotation", "Unknown")
        rotation_dist[rot] = rotation_dist.get(rot, 0) + 1

    # Class aggregations
    class_dist: dict = {"Strong-Bullish": 0, "Bullish": 0, "Neutral": 0,
                          "Weak": 0, "Bearish": 0, "Unknown": 0}
    for i in computed:
        c = i.get("classification", "Unknown")
        class_dist[c] = class_dist.get(c, 0) + 1

    top3 = computed[:3]
    bottom3 = computed[-3:]

    warnings = []
    for i in non_computed:
        warnings.append(f"industry {i['industry_key']}: {i.get('status')} "
                         f"({i.get('n_used', 0)}/{i.get('n_defined', 0)} constituents)")

    return {
        "asof_date_ist":            _asof_ist(asof_iso),
        "asof_utc":                 asof_iso,
        "published_at_utc":         _now_utc_iso(),
        "code_sha":                 code_sha,
        "schema_version":           "ARCH017A v1.0-draft",
        "weighting_version":        "DEV019 v1.0",
        "dev_version":              "DEV019 v0.1",
        "upstream_global_context": {
            "available": global_ctx is not None,
            "asof_utc": global_ctx.get("asof_utc") if global_ctx else None,
            "global_risk":  (global_ctx.get("composites", {}).get("global_risk", {}).get("value_0_100")
                              if global_ctx else None),
            "global_posture": (global_ctx.get("classifications", {}).get("global_posture", {}).get("label")
                                if global_ctx else None),
        },
        "upstream_sector_context": {
            "available": sector_ctx is not None,
            "asof_utc": sector_ctx.get("asof_utc") if sector_ctx else None,
            "sectors_computed": sector_ctx.get("portfolio_level", {}).get("sectors_computed")
                                 if sector_ctx else None,
        },
        "industries": industries_final,
        "portfolio_level": {
            "industries_computed": len(computed),
            "industries_total":    len(industries_out),
            "average_score":       round(sum(i["score"] for i in computed) / len(computed), 2) if computed else None,
            "top3_industries":     [{"key": i["industry_key"], "display": i["display_name"],
                                        "score": i["score"], "classification": i["classification"],
                                        "rotation": i["rotation"],
                                        "parent_sector": i["parent_sector_name"]} for i in top3],
            "bottom3_industries":  [{"key": i["industry_key"], "display": i["display_name"],
                                        "score": i["score"], "classification": i["classification"],
                                        "rotation": i["rotation"],
                                        "parent_sector": i["parent_sector_name"]} for i in bottom3],
            "class_distribution":  class_dist,
            "rotation_distribution": rotation_dist,
        },
        "warnings":                 warnings,
        "summary_counts": {
            "derived_metrics":       compute_result.get("derived_count", 0),
            "normalized_indicators": compute_result.get("normalized_count", 0),
            "classifications":       compute_result.get("classifications_count", 0),
            "composites":            compute_result.get("composites_count", 0),
        },
    }


def write_bundle(bundle: dict) -> tuple[Path, Path]:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    json_path = PUBLISH_DIR / "industry_context.json"
    parquet_path = PUBLISH_DIR / "industry_context.parquet"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, default=str)

    rows = []
    for i in bundle["industries"]:
        if i.get("status") != "computed":
            continue
        rows.append({
            "asof_date_ist":   bundle["asof_date_ist"],
            "asof_utc":        bundle["asof_utc"],
            "industry_key":    i["industry_key"],
            "display_name":    i["display_name"],
            "parent_sector":   i["parent_sector_name"],
            "score":           i["score"],
            "classification":  i["classification"],
            "rotation":        i["rotation"],
            "confidence":      i["confidence"],
            "leadership_rank": i["leadership_rank"],
            "intra_sector_rank": i["intra_sector_rank"],
            "intra_sector_total": i["intra_sector_total"],
            "n_used":          i["n_used"],
        })
    if rows:
        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    return json_path, parquet_path
