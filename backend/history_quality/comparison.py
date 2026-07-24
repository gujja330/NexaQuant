"""Sprint B0 · Cross-market comparison (reports/global/history_quality_comparison.json)."""
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .types import QualityReport


def build_comparison(*, india: QualityReport, usa: QualityReport,
                        output_path: Path) -> Dict[str, Any]:
    """Compose India+USA reports into a single global comparison artifact."""

    def _by_family(r: QualityReport) -> Dict[str, Dict[str, Any]]:
        return {res.family: {
            "status": res.status,
            "exists": res.exists,
            "n_rows": res.n_rows,
            "quality_score": res.quality_score,
            "date_range": res.date_range,
        } for res in r.per_family}

    india_map = _by_family(india)
    usa_map = _by_family(usa)
    all_families = sorted(set(india_map.keys()) | set(usa_map.keys()))

    per_family_delta = []
    for f in all_families:
        i = india_map.get(f, {})
        u = usa_map.get(f, {})
        per_family_delta.append({
            "family": f,
            "india_status": i.get("status"), "usa_status": u.get("status"),
            "india_n_rows": i.get("n_rows", 0), "usa_n_rows": u.get("n_rows", 0),
            "india_quality_score": i.get("quality_score", 0),
            "usa_quality_score": u.get("quality_score", 0),
            "delta_rows_usa_minus_india": u.get("n_rows", 0) - i.get("n_rows", 0),
            "delta_score_usa_minus_india": u.get("quality_score", 0) - i.get("quality_score", 0),
        })

    payload = {
        "engine": "aegis.history_quality.v1",
        "version": "1.0.0",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "india": {
            "verdict": india.verdict,
            "overall_quality_score": india.overall_quality_score,
            "counts": {"PASS": india.n_pass, "WARN": india.n_warn,
                          "FAIL": india.n_fail, "NOT_APPLICABLE": india.n_not_applicable},
            "corporate_action_flags": india.corporate_action_flags,
        },
        "usa": {
            "verdict": usa.verdict,
            "overall_quality_score": usa.overall_quality_score,
            "counts": {"PASS": usa.n_pass, "WARN": usa.n_warn,
                          "FAIL": usa.n_fail, "NOT_APPLICABLE": usa.n_not_applicable},
            "corporate_action_flags": usa.corporate_action_flags,
        },
        "delta": {
            "overall_score_usa_minus_india": usa.overall_quality_score - india.overall_quality_score,
            "verdict_match": india.verdict == usa.verdict,
        },
        "per_family": per_family_delta,
        "worse_market_overall": (
            "india" if india.overall_quality_score < usa.overall_quality_score
            else ("usa" if usa.overall_quality_score < india.overall_quality_score else "tied")
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload
