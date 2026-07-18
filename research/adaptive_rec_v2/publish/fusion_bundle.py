"""Adaptive Rec Engine v2.1 · Fusion publish."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, tuple):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if np.isnan(v) or np.isinf(v) else v
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    return obj


def build_and_publish(result: dict) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    reports = result["reports"]

    # 1. investment_intelligence.json — full per-ticker report
    with (REPORTS / "investment_intelligence.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "code_sha":        result["code_sha"],
            "engine":          result["engine"],
            "version":         result["version"],
            "as_of":           result["as_of"],
            "weights":         result["weights"],
            "n_recs":          len(reports),
            "reports":         reports,
            "governance":      result["governance"],
        }), f, indent=2, default=str)

    # 2. investment_intelligence.parquet — flat table
    flat = []
    for r in reports:
        row = {
            "ticker":              r["ticker"],
            "sector":              r["sector"],
            "raw_recommendation":  r["raw_recommendation"],
            "raw_composite_score": r["raw_composite_score"],
            "intelligence_score":  r["intelligence_score"],
            "fusion_decision":     r["fusion_decision"],
            "n_dims_used":         r["n_dimensions_used"],
            "n_dims_missing":      r["n_dimensions_missing"],
            "conflict_severity":   r["conflict_severity"],
            "top_contributors":    " · ".join(r["top_contributors"] or []),
            "bottom_contributors": " · ".join(r["bottom_contributors"] or []),
        }
        # flatten dimension scores as columns for quick sorting
        for d in r["dimensions"]:
            row[f"dim_{d['name']}"] = d["score"]
        flat.append(row)
    pd.DataFrame(flat).to_parquet(REPORTS / "investment_intelligence.parquet", index=False)

    # 3. intelligence_explanation.json — top-K + bottom-K + why panels
    top20 = sorted(reports, key=lambda r: -(r["intelligence_score"] or 0))[:20]
    bot10 = sorted(reports, key=lambda r: (r["intelligence_score"] or 0))[:10]
    with (REPORTS / "intelligence_explanation.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       result["run_utc"],
            "top_20":        [{"ticker": r["ticker"],
                                 "score": r["intelligence_score"],
                                 "decision": r["fusion_decision"],
                                 "why_this": r["why_this"],
                                 "why_not_stronger": r["why_not_stronger"],
                                 "top_contributors": r["top_contributors"],
                                 "conflicts": r["conflicts"]}
                                for r in top20],
            "bottom_10":     [{"ticker": r["ticker"],
                                 "score": r["intelligence_score"],
                                 "decision": r["fusion_decision"],
                                 "why_this": r["why_this"],
                                 "why_not_stronger": r["why_not_stronger"],
                                 "bottom_contributors": r["bottom_contributors"],
                                 "conflicts": r["conflicts"]}
                                for r in bot10],
        }), f, indent=2, default=str)

    # 4. intelligence_conflicts.json — full conflict register
    all_conflicts = []
    for r in reports:
        for c in (r["conflicts"] or []):
            all_conflicts.append({**c, "ticker": r["ticker"],
                                       "raw_recommendation": r["raw_recommendation"],
                                       "fusion_decision": r["fusion_decision"],
                                       "intelligence_score": r["intelligence_score"]})
    with (REPORTS / "intelligence_conflicts.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "summary":         result["conflict_summary"],
            "all_conflicts":   all_conflicts,
        }), f, indent=2, default=str)

    # 5. intelligence_summary.json — one-page portfolio-level snapshot
    with (REPORTS / "intelligence_summary.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":            result["run_utc"],
            "engine":             result["engine"],
            "version":            result["version"],
            "n_recs":             result["summary"]["n_recs"],
            "n_scored":           result["summary"]["n_scored"],
            "avg_intelligence":   result["summary"]["avg_intelligence"],
            "median_intelligence": result["summary"]["median_intelligence"],
            "by_decision":        result["summary"]["by_decision"],
            "top_10":             [{"ticker": r["ticker"],
                                      "score": r["intelligence_score"],
                                      "decision": r["fusion_decision"],
                                      "raw_recommendation": r["raw_recommendation"]}
                                     for r in result["summary"]["top_10"]],
            "conflict_summary":   result["conflict_summary"],
            "weights":            result["weights"],
            "governance":         result["governance"],
        }), f, indent=2, default=str)

    return {
        "written": [
            "investment_intelligence.json",
            "investment_intelligence.parquet",
            "intelligence_explanation.json",
            "intelligence_conflicts.json",
            "intelligence_summary.json",
        ],
        "n_recs":          len(reports),
        "avg_score":       result["summary"]["avg_intelligence"],
        "n_critical":      result["conflict_summary"]["n_critical"],
        "n_medium":        result["conflict_summary"]["n_medium"],
    }
