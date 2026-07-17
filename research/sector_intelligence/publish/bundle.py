"""DEV018 publish — produces reports/sector_context.json (+ parquet mirror).

Format follows ARCH018 §17.1 output-contract shape.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _asof_ist(asof_utc_iso: str) -> str:
    from datetime import timedelta
    utc = datetime.fromisoformat(asof_utc_iso.replace("Z", "+00:00"))
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def build_bundle(compute_result: dict, code_sha: str = "nogit") -> dict:
    per_sector = compute_result.get("_per_sector", [])
    global_ctx = compute_result.get("_global_context")
    asof_iso = compute_result.get("asof_utc", _now_utc_iso())

    sectors_out = []
    for entry in per_sector:
        if entry["status"] != "computed":
            sectors_out.append({
                "sector_key": entry["sector_key"],
                "display_name": entry["display_name"],
                "status": entry["status"],
            })
            continue
        composite = entry["composite"]
        components = list(composite.component_indicators)
        # Rank top drivers by contribution
        components_sorted = sorted(components,
                                     key=lambda x: x["contribution_to_composite"], reverse=True)
        top_drivers = [{"indicator": c["indicator_key"],
                          "value_0_100": c["value_0_100"],
                          "weight": c["weight"],
                          "contribution": c["contribution_to_composite"]}
                         for c in components_sorted[:5]]
        detractors = [c for c in components if c["value_0_100"] < 40]
        detractors_sorted = sorted(detractors, key=lambda x: x["value_0_100"])[:3]
        sectors_out.append({
            "sector_key": entry["sector_key"],
            "display_name": entry["display_name"],
            "status": "computed",
            "score": composite.value_0_100,
            "classification": composite.classification,
            "confidence": composite.confidence,
            "n_constituents_used": entry.get("n_constituents_used", 0),
            "top_drivers": top_drivers,
            "top_detractors": [{"indicator": d["indicator_key"], "value_0_100": d["value_0_100"]}
                                  for d in detractors_sorted],
            "weighting_version": composite.weighting_version,
        })

    # Sort sectors by score descending (best-first)
    computed = [s for s in sectors_out if s.get("status") == "computed"]
    computed.sort(key=lambda x: x["score"], reverse=True)
    non_computed = [s for s in sectors_out if s.get("status") != "computed"]
    sectors_final = computed + non_computed

    # Portfolio-level roll-ups
    if computed:
        score_values = [s["score"] for s in computed]
        top3 = computed[:3]
        bottom3 = computed[-3:]
    else:
        score_values = []
        top3 = []
        bottom3 = []

    warnings = []
    for s in non_computed:
        warnings.append(f"sector {s['sector_key']} status: {s.get('status')}")

    bundle = {
        "asof_date_ist":           _asof_ist(asof_iso),
        "asof_utc":                asof_iso,
        "published_at_utc":        _now_utc_iso(),
        "code_sha":                code_sha,
        "schema_version":          "ARCH017A v1.0-draft",
        "weighting_version":       "ARCH018 v1.0-draft",
        "dev_version":             "DEV018 v0.1",
        "upstream_global_context": {
            "available": global_ctx is not None,
            "asof_utc":     global_ctx.get("asof_utc") if global_ctx else None,
            "global_risk":  (global_ctx.get("composites", {}).get("global_risk", {}).get("value_0_100")
                              if global_ctx else None),
            "global_posture": (global_ctx.get("classifications", {}).get("global_posture", {}).get("label")
                                if global_ctx else None),
        },
        "sectors":                 sectors_final,
        "portfolio_level": {
            "sectors_computed":  len(computed),
            "sectors_total":     len(sectors_out),
            "average_score":     round(sum(score_values) / len(score_values), 2) if score_values else None,
            "top3_sectors":      [{"key": s["sector_key"], "score": s["score"],
                                      "classification": s["classification"]} for s in top3],
            "bottom3_sectors":   [{"key": s["sector_key"], "score": s["score"],
                                      "classification": s["classification"]} for s in bottom3],
            "class_distribution": _class_distribution(computed),
        },
        "warnings":                warnings,
        "summary_counts": {
            "derived_metrics":       compute_result.get("derived_count", 0),
            "normalized_indicators": compute_result.get("normalized_count", 0),
            "classifications":       compute_result.get("classifications_count", 0),
            "composites":            compute_result.get("composites_count", 0),
        },
    }
    return bundle


def _class_distribution(computed: list[dict]) -> dict:
    dist = {"Strong-Bullish": 0, "Bullish": 0, "Neutral": 0, "Weak": 0, "Bearish": 0, "Unknown": 0}
    for s in computed:
        cls = s.get("classification", "Unknown")
        dist[cls] = dist.get(cls, 0) + 1
    return dist


def write_bundle(bundle: dict) -> tuple[Path, Path]:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    json_path = PUBLISH_DIR / "sector_context.json"
    parquet_path = PUBLISH_DIR / "sector_context.parquet"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, default=str)

    # Flat parquet: one row per sector
    rows = []
    for s in bundle["sectors"]:
        if s.get("status") != "computed":
            continue
        rows.append({
            "asof_date_ist":   bundle["asof_date_ist"],
            "asof_utc":        bundle["asof_utc"],
            "sector_key":      s["sector_key"],
            "display_name":    s["display_name"],
            "score":           s["score"],
            "classification":  s["classification"],
            "confidence":      s["confidence"],
            "top_driver_1":    s["top_drivers"][0]["indicator"] if s["top_drivers"] else None,
            "top_driver_2":    s["top_drivers"][1]["indicator"] if len(s["top_drivers"]) > 1 else None,
            "top_driver_3":    s["top_drivers"][2]["indicator"] if len(s["top_drivers"]) > 2 else None,
            "n_constituents":  s.get("n_constituents_used", 0),
        })
    if rows:
        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    return json_path, parquet_path
