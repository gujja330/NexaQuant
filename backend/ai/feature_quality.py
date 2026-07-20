"""AI Feature Quality Agent v1.0.

Reads a FeatureValidationResult. Narrates completeness per category,
identifies the categories with weakest coverage, and states whether
downstream engines can safely consume the snapshot. No recommendations.
"""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput
from backend.feature_store.feature_validation import FeatureValidationResult

VERSION = "v1.0"


def run(val: FeatureValidationResult, market_name: str,
         asof: date | None = None) -> AgentOutput:
    if val is None or val.n_rows == 0:
        return AgentOutput(agent="feature_quality", version=VERSION, market=market_name,
                             asof=asof or date.today(),
                             headline="Empty snapshot — cannot assess quality",
                             narrative="No rows in the Feature Store snapshot.",
                             confidence=0.0,
                             caveats=["Empty"])

    v = val.verdict
    verdict_line = {
        "PASS":     f"Feature Store quality PASS · {val.n_rows} rows · {val.n_features} features.",
        "WARNING":  f"Feature Store quality WARNING · overall null rate {val.null_pct_overall:.1%}.",
        "FAIL":     f"Feature Store quality FAIL · overall null rate {val.null_pct_overall:.1%} exceeds threshold.",
    }[v]

    # Categories ranked by coverage
    cov_lines = []
    for cat, cov in sorted(val.coverage_per_category.items(), key=lambda kv: kv[1]):
        cov_lines.append(f"  · {cat:<18} avg coverage {cov:.1%}")

    weakest = min(val.coverage_per_category.items(), key=lambda kv: kv[1],
                    default=(None, None))
    strongest = max(val.coverage_per_category.items(), key=lambda kv: kv[1],
                      default=(None, None))

    weakness_line = ""
    if weakest[0] and weakest[1] is not None:
        if weakest[1] < 0.30:
            weakness_line = (f"Weakest category is '{weakest[0]}' at {weakest[1]:.1%} coverage — "
                              "downstream engines relying on this category should degrade gracefully.")
        elif weakest[1] < 0.60:
            weakness_line = (f"Weakest category is '{weakest[0]}' at {weakest[1]:.1%} coverage — "
                              "acceptable but flagged for follow-up.")

    strength_line = ""
    if strongest[0] and strongest[1] is not None and strongest[1] > 0.90:
        strength_line = f"Strongest category is '{strongest[0]}' at {strongest[1]:.1%} coverage — solid."

    outlier_line = ""
    if val.outliers_flagged:
        outlier_line = (f"{len(val.outliers_flagged)} feature column(s) show |z|>8 extremes — "
                         "see the Feature Anomaly agent for detail.")

    parts = [verdict_line]
    if cov_lines:
        parts.append("Category coverage:\n" + "\n".join(cov_lines))
    if strength_line: parts.append(strength_line)
    if weakness_line: parts.append(weakness_line)
    if outlier_line:  parts.append(outlier_line)

    return AgentOutput(
        agent="feature_quality", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=verdict_line,
        narrative="\n\n".join(parts),
        findings=[{"category": c, "coverage": v} for c, v in val.coverage_per_category.items()],
        evidence={"verdict": v, "null_pct_overall": val.null_pct_overall,
                    "n_rows": val.n_rows, "n_features": val.n_features,
                    "n_outliers": len(val.outliers_flagged)},
        citations=["backend/feature_store/feature_validation.py"],
        confidence=1.0 if v == "PASS" else (0.7 if v == "WARNING" else 0.5),
        caveats=[],
        determinism="template",
    )
