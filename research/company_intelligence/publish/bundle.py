"""DEV020 publish — reports/company_context.json + parquet mirror."""
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
    per_company = compute_result.get("_per_company", [])
    asof_iso = compute_result.get("asof_utc", _now_utc_iso())

    companies_out = []
    for entry in per_company:
        if entry["status"] != "computed":
            companies_out.append({
                "ticker": entry["ticker"],
                "status": entry["status"],
                "reason": entry.get("reason"),
                "industry_key": entry.get("industry_key"),
                "parent_sector_key": entry.get("parent_sector_key"),
            })
            continue

        composite = entry["composite"]
        components = list(composite.component_indicators)
        sorted_c = sorted(components, key=lambda x: x["contribution_to_composite"], reverse=True)
        positive_drivers = [{"indicator": c["indicator_key"],
                                "value_0_100": c["value_0_100"],
                                "weight": c["weight"],
                                "contribution": c["contribution_to_composite"]}
                               for c in sorted_c[:5]]

        # Negative drivers = lowest-value dimensions
        sorted_asc = sorted(components, key=lambda x: x["value_0_100"])
        negative_drivers = [{"indicator": c["indicator_key"],
                                "value_0_100": c["value_0_100"],
                                "contribution": c["contribution_to_composite"]}
                               for c in sorted_asc[:3] if c["value_0_100"] < 50]

        # Largest strengths (top by value_0_100)
        sorted_desc = sorted(components, key=lambda x: x["value_0_100"], reverse=True)
        strengths = [{"indicator": c["indicator_key"],
                        "value_0_100": c["value_0_100"]}
                       for c in sorted_desc[:3] if c["value_0_100"] >= 70]

        # Largest risks (volatility + drawdown low values)
        risks = []
        for c in components:
            if c["indicator_key"] in ("norm.company.volatility", "norm.company.drawdown") \
                    and c["value_0_100"] < 40:
                risks.append({"indicator": c["indicator_key"],
                                "value_0_100": c["value_0_100"]})

        companies_out.append({
            "ticker": entry["ticker"],
            "status": "computed",
            "score": composite.value_0_100,
            "classification": composite.classification,
            "confidence": composite.confidence,
            "latest_close": entry["latest_close"],
            "history_bars": entry["history_bars"],

            # Full hierarchy inheritance
            "hierarchy": {
                "global_score":       entry.get("inherited_global_score"),
                "global_posture":     entry.get("inherited_global_posture"),
                "sector_key":         entry["parent_sector_key"],
                "sector_display":     entry["parent_sector_display"],
                "sector_score":       entry.get("inherited_sector_score"),
                "sector_classification": entry.get("inherited_sector_class"),
                "industry_key":       entry["industry_key"],
                "industry_display":   entry["industry_display"],
                "industry_score":     entry.get("inherited_industry_score"),
                "industry_classification": entry.get("inherited_industry_class"),
            },

            # Rankings
            "rankings": {
                "overall_rank":  entry.get("overall_rank"),
                "sector_rank":   entry.get("sector_rank"),
                "sector_total":  entry.get("sector_total"),
                "industry_rank": entry.get("industry_rank"),
                "industry_total": entry.get("industry_total"),
                "rs_rank":       entry.get("rs_rank"),
                "risk_rank":     entry.get("risk_rank"),
            },

            "positive_drivers":  positive_drivers,
            "negative_drivers":  negative_drivers,
            "largest_strengths": strengths,
            "largest_risks":     risks,
            "weighting_version": composite.weighting_version,
        })

    computed = [c for c in companies_out if c.get("status") == "computed"]
    non_computed = [c for c in companies_out if c.get("status") != "computed"]
    computed.sort(key=lambda x: x["rankings"]["overall_rank"])
    companies_final = computed + non_computed

    class_dist = {"Strong-Bullish": 0, "Bullish": 0, "Neutral": 0,
                    "Weak": 0, "Bearish": 0, "Unknown": 0}
    for c in computed:
        class_dist[c["classification"]] = class_dist.get(c["classification"], 0) + 1

    # Sector aggregates
    sector_summary: dict[str, dict] = {}
    for c in computed:
        sec = c["hierarchy"]["sector_display"] or "Unknown"
        d = sector_summary.setdefault(sec, {"n": 0, "avg_score": 0.0, "top_ticker": None,
                                              "top_score": 0.0})
        d["n"] += 1
        d["avg_score"] += c["score"]
        if c["score"] > d["top_score"]:
            d["top_score"] = c["score"]
            d["top_ticker"] = c["ticker"]
    for d in sector_summary.values():
        d["avg_score"] = round(d["avg_score"] / d["n"], 2) if d["n"] > 0 else 0

    top_10 = [{"ticker": c["ticker"], "score": c["score"],
                 "classification": c["classification"],
                 "sector": c["hierarchy"]["sector_display"],
                 "industry": c["hierarchy"]["industry_display"]}
                for c in computed[:10]]

    bottom_10 = [{"ticker": c["ticker"], "score": c["score"],
                    "classification": c["classification"],
                    "sector": c["hierarchy"]["sector_display"],
                    "industry": c["hierarchy"]["industry_display"]}
                   for c in computed[-10:]]

    warnings = []
    rej = compute_result.get("rejections", {})
    for reason, count in rej.items():
        warnings.append(f"{count} tickers rejected: {reason}")

    return {
        "asof_date_ist":            _asof_ist(asof_iso),
        "asof_utc":                 asof_iso,
        "published_at_utc":         _now_utc_iso(),
        "code_sha":                 code_sha,
        "schema_version":           "ARCH017A v1.0-draft",
        "weighting_version":        "DEV020 v1.0",
        "dev_version":              "DEV020 v0.1",
        "companies":                companies_final,
        "portfolio_level": {
            "companies_computed": len(computed),
            "companies_rejected": len(non_computed),
            "companies_total":    len(companies_out),
            "average_score":      round(sum(c["score"] for c in computed) / len(computed), 2)
                                   if computed else None,
            "class_distribution": class_dist,
            "top_10":             top_10,
            "bottom_10":          bottom_10,
            "sector_summary":     sector_summary,
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
    json_path = PUBLISH_DIR / "company_context.json"
    parquet_path = PUBLISH_DIR / "company_context.parquet"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, default=str)

    rows = []
    for c in bundle["companies"]:
        if c.get("status") != "computed":
            continue
        h = c["hierarchy"]
        r = c["rankings"]
        rows.append({
            "asof_date_ist":         bundle["asof_date_ist"],
            "asof_utc":              bundle["asof_utc"],
            "ticker":                c["ticker"],
            "score":                 c["score"],
            "classification":        c["classification"],
            "confidence":            c["confidence"],
            "sector":                h["sector_display"],
            "sector_score":          h["sector_score"],
            "sector_class":          h["sector_classification"],
            "industry":              h["industry_display"],
            "industry_score":        h["industry_score"],
            "industry_class":        h["industry_classification"],
            "global_posture":        h["global_posture"],
            "overall_rank":          r["overall_rank"],
            "sector_rank":           r["sector_rank"],
            "industry_rank":         r["industry_rank"],
            "rs_rank":               r["rs_rank"],
            "risk_rank":             r["risk_rank"],
        })
    if rows:
        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    return json_path, parquet_path
