"""Adaptive Rec Engine v2.1 · Intelligence Fusion orchestrator.

Loads every upstream engine's published artifacts once, then fuses
the 10 dimensions per recommendation. Emits a per-rec Intelligence
Report, a conflict register, and a portfolio-level summary."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from adaptive_rec_v2.lib import dimensions, fusion, conflicts                          # noqa: E402


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load_context() -> dict:
    """Pre-load every upstream artifact so per-rec fusion is O(1) per dim."""
    def _read(name: str):
        p = _ROOT / "reports" / name
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _read_pq(name: str):
        p = _ROOT / "reports" / name
        if not p.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(p)
        except Exception:
            return pd.DataFrame()

    return {
        "learning":        _read_pq("learning.parquet"),
        "validation":      _read("validation_v2_latest.json"),
        "risk":            _read("risk_capital_v2_latest.json"),
        "entity_network":  _read("entity_network.json"),
        "dna_feedback":    _read("recommendation_dna_feedback.json"),
        "calibration":     _read("confidence_calibration.json"),
        "rec_paths":       _read("recommendation_paths.json"),
    }


def _load_recs() -> list[dict]:
    p = _ROOT / "reports" / "recommendations.json"
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).get("recommendations") or [])
    except Exception:
        return []


def run(verbose: bool = True) -> dict:
    recs = _load_recs()
    if not recs:
        return {"error": "no reports/recommendations.json — run DEV023 first"}

    ctx = _load_context()
    if verbose:
        avail = {k: (v is not None and not (hasattr(v, "empty") and v.empty))
                    for k, v in ctx.items()}
        print(f"  upstream availability: " + ", ".join(f"{k}={'Y' if v else 'N'}" for k, v in avail.items()))

    weights = fusion.load_weights()
    if verbose:
        print(f"  fusion weights: {weights}")

    per_ticker_reports = []
    per_ticker_conflicts: dict[str, list[dict]] = {}

    for rec in recs:
        dims = dimensions.score_all_dimensions(rec, ctx)
        fused = fusion.fuse(dims, weights)
        rec_conflicts = conflicts.detect_conflicts(rec, dims, fused)

        report = {
            "ticker":              rec.get("ticker"),
            "sector":              rec.get("sector"),
            "industry":            rec.get("industry"),
            "raw_recommendation":  rec.get("recommendation"),
            "raw_composite_score": rec.get("composite_decision_score"),
            "raw_confidence":      rec.get("confidence"),

            "intelligence_score":  fused["intelligence_score"],
            "fusion_decision":     fused["decision"],

            "dimensions":          dimensions.dimensions_to_dict(dims),
            "contributions":       fused["contributions"],
            "top_contributors":    fused["top_contributors"],
            "bottom_contributors": fused["bottom_contributors"],
            "n_dimensions_used":   fused["n_dimensions_used"],
            "n_dimensions_missing":fused["n_dimensions_missing"],
            "missing_dimensions":  fused.get("missing_dimensions", []),

            "why_this":            fusion.why_this_recommendation(dims),
            "why_not_stronger":    fusion.why_not_stronger(dims),

            "conflicts":           rec_conflicts,
            "conflict_severity":   ("CRITICAL" if any(c["severity"] == "CRITICAL" for c in rec_conflicts)
                                     else "MEDIUM"   if any(c["severity"] == "MEDIUM"   for c in rec_conflicts)
                                     else "MINOR"    if rec_conflicts
                                     else "NONE"),
        }
        per_ticker_reports.append(report)
        if rec_conflicts:
            per_ticker_conflicts[str(rec.get("ticker"))] = rec_conflicts

    if verbose:
        by_dec: dict[str, int] = {}
        for r in per_ticker_reports:
            d = r["fusion_decision"] or "?"
            by_dec[d] = by_dec.get(d, 0) + 1
        print(f"  fusion decision distribution: " +
                " · ".join(f"{k}={v}" for k, v in sorted(by_dec.items())))
        n_crit = sum(1 for r in per_ticker_reports if r["conflict_severity"] == "CRITICAL")
        n_med  = sum(1 for r in per_ticker_reports if r["conflict_severity"] == "MEDIUM")
        n_min  = sum(1 for r in per_ticker_reports if r["conflict_severity"] == "MINOR")
        print(f"  conflicts: {n_crit} CRITICAL · {n_med} MEDIUM · {n_min} MINOR")

    conflict_summary = conflicts.aggregate_conflicts(per_ticker_conflicts)

    # Portfolio-level summary
    scores = [r["intelligence_score"] for r in per_ticker_reports
                if r["intelligence_score"] is not None]
    summary = {
        "n_recs":                len(per_ticker_reports),
        "n_scored":              len(scores),
        "avg_intelligence":      round(float(np.mean(scores)), 2) if scores else None,
        "median_intelligence":   round(float(np.median(scores)), 2) if scores else None,
        "top_10":                sorted(per_ticker_reports,
                                          key=lambda r: -(r["intelligence_score"] or 0))[:10],
        "bottom_10":             sorted(per_ticker_reports,
                                          key=lambda r: (r["intelligence_score"] or 0))[:10],
        "by_decision":           {},
    }
    for r in per_ticker_reports:
        d = r["fusion_decision"] or "?"
        summary["by_decision"][d] = summary["by_decision"].get(d, 0) + 1

    return {
        "run_utc":            datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":           _git_sha(),
        "engine":             "Adaptive Recommendation Engine",
        "version":            "v2.1 · Intelligence Fusion",
        "as_of":              date.today().isoformat(),
        "weights":            weights,
        "reports":            per_ticker_reports,
        "summary":            summary,
        "conflict_summary":   conflict_summary,
        "governance":         ("Advisory only. Fusion is a decision-support signal, "
                                "not a directive. Every dimension carries an explanation "
                                "and every conflict is named. Weights are configurable via "
                                "reports/fusion_weights.json."),
    }
