"""AEGIS USA · Intelligence Fusion v1.0.

USA equivalent of India's Fusion v2.1. Aggregates the 6 technical
dimensions from recommendations.json into a per-ticker intelligence
report with:

  intelligence_score  — same as composite_decision_score for now
                        (until an ML calibration layer arrives)
  fusion_decision     — same as recommendation
  dimensions[]        — the 6 technical dims restructured
  why_this            — top 3 positive dims with humanized explanations
  why_not_stronger    — top 2 negative dims
  top_contributors    — dims ranked by weighted contribution
  conflicts           — any inversions (e.g. score high but trend low)

Emits usa/reports/investment_intelligence.json + intelligence_summary.json.
Same schemas India uses so downstream consumers work symmetrically.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]


DIM_LABELS = {
    "dim_momentum":     "Momentum",
    "dim_trend":        "Trend",
    "dim_rs_spx":       "Relative Strength (vs S&P 500)",
    "dim_volatility":   "Volatility (inverted)",
    "dim_drawdown":     "Drawdown (inverted)",
    "dim_position_52w": "52-Week Position",
}
DIM_WHY = {
    "dim_momentum":     "Strong 20-day price momentum",
    "dim_trend":        "SMA20 above SMA50 — trend is up",
    "dim_rs_spx":       "Outperforming the S&P 500 over 20 days",
    "dim_volatility":   "Volatility inside a healthy band",
    "dim_drawdown":     "Modest drawdown from 52-week peak",
    "dim_position_52w": "Trading near the top of the 52-week range",
}
DIM_WHY_NOT = {
    "dim_momentum":     "Weak 20-day price momentum",
    "dim_trend":        "SMA20 below SMA50 — no clear uptrend",
    "dim_rs_spx":       "Lagging the S&P 500 over 20 days",
    "dim_volatility":   "Volatility elevated — risk-adjusted return suspect",
    "dim_drawdown":     "Deep drawdown from 52-week peak",
    "dim_position_52w": "Trading near the bottom of the 52-week range",
}


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Intelligence Fusion v1.0")
    print("=" * 70)

    recs_p = _USA / "reports" / "recommendations.json"
    if not recs_p.exists():
        print("FATAL: recommendations.json missing.")
        return 1
    recs = json.loads(recs_p.read_text(encoding="utf-8"))

    reports: list[dict] = []
    scores: list[float] = []
    conflicts_all: list[dict] = []

    for r in (recs.get("recommendations") or []):
        t = str(r.get("ticker"))
        dims = r.get("dimensions") or {}
        intel = r.get("composite_decision_score")

        # Ranked contributors — top / bottom dimensions
        by_score = sorted(
            ((k, v) for k, v in dims.items() if isinstance(v, (int, float))),
            key=lambda kv: -kv[1],
        )
        why_this: list[dict] = []
        for k, v in by_score[:3]:
            if v >= 55:
                why_this.append({"name": k.replace("dim_", ""), "score": v,
                                 "why": DIM_WHY.get(k, k)})
        why_not: list[dict] = []
        for k, v in by_score[-2:]:
            if v < 45:
                why_not.append({"name": k.replace("dim_", ""), "score": v,
                                "why": DIM_WHY_NOT.get(k, k)})

        # Contributors: dims weighted by their score share of total
        total = sum(v for _, v in by_score) or 1.0
        top_contributors = [
            {"name": k.replace("dim_", ""), "score": v,
             "contribution": round(v / total, 4)}
            for k, v in by_score[:4]
        ]

        # Conflicts — high overall score but weak in a critical dim
        conflicts: list[dict] = []
        if intel and intel >= 70:
            for k, v in dims.items():
                if isinstance(v, (int, float)) and v < 30:
                    conflicts.append({
                        "ticker": t, "rule": "high_intel_with_weak_dim",
                        "severity": "MEDIUM",
                        "detail": f"Intel {intel} but {k}={v}",
                    })
        conflicts_all.extend(conflicts)

        reports.append({
            "ticker":              t,
            "sector":              r.get("sector"),
            "intelligence_score":  intel,
            "fusion_decision":     r.get("recommendation"),
            "dimensions":          [{"name": k.replace("dim_", ""), "score": v,
                                       "why": (DIM_WHY if v >= 50 else DIM_WHY_NOT).get(k, k)}
                                      for k, v in dims.items() if isinstance(v, (int, float))],
            "why_this":            why_this,
            "why_not_stronger":    why_not,
            "top_contributors":    top_contributors,
            "conflicts":           conflicts,
        })
        if intel is not None:
            scores.append(intel)

    # Summary
    n_critical = sum(1 for c in conflicts_all if c.get("severity") == "CRITICAL")
    n_medium   = sum(1 for c in conflicts_all if c.get("severity") == "MEDIUM")

    summary = {
        "engine":              "usa_intelligence_fusion",
        "version":             "v1.0",
        "market":              "USA",
        "run_utc":             datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "n_scored":            len(scores),
        "avg_intelligence":    round(sum(scores) / len(scores), 2) if scores else None,
        "median_intelligence": round(sorted(scores)[len(scores) // 2], 2) if scores else None,
        "conflict_summary": {
            "n_conflicts": len(conflicts_all),
            "n_critical":  n_critical,
            "n_medium":    n_medium,
        },
    }
    (_USA / "reports" / "intelligence_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")

    out = {
        "engine":  "usa_intelligence_fusion",
        "version": "v1.0",
        "market":  "USA",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "reports": reports,
    }
    (_USA / "reports" / "investment_intelligence.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    conflicts_out = {
        "engine":         "usa_intelligence_conflicts",
        "version":        "v1.0",
        "run_utc":        datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "all_conflicts":  conflicts_all,
        "n_total":        len(conflicts_all),
    }
    (_USA / "reports" / "intelligence_conflicts.json").write_text(
        json.dumps(conflicts_out, indent=2, default=str), encoding="utf-8")

    print(f"  scored:            {len(scores)} / {len(reports)}")
    print(f"  avg intelligence:  {summary['avg_intelligence']}")
    print(f"  conflicts:         {len(conflicts_all)} ({n_critical} critical, {n_medium} medium)")
    print(f"  elapsed:           {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
