"""AI Learning Analyst v1.0 — descriptive audit of the learning corpus.

Reads LearningEngineResult. Emits:
  - Corpus health (n_rows, n_winners, win_rate, avg_return)
  - Top-3 alpha-generating models (by net_alpha)
  - Top-3 alpha-destroying models (deprecation candidates)
  - Top-5 features by |net_alpha|
  - Failure clusters (top 3 by n_members)
  - Calibration health (method, RMS error)

Never emits buy/sell/promoted/approved keys (contract-tested).
"""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput
from backend.learning.engine import LearningEngineResult

VERSION = "v1.0"


def run(result: LearningEngineResult, market_name: str,
         asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Corpus health
    findings.append({
        "type":              "corpus_health",
        "n_recs_in_history": result.n_recs_in_history,
        "n_new_closed":      result.n_new_closed,
        "n_corpus_total":    result.n_corpus_total,
        "n_winners":         result.n_winners,
        "n_losers":          result.n_losers,
        "win_rate":          result.win_rate,
        "avg_return":        result.avg_return,
        "horizon_days":      result.horizon_days,
    })

    # Empty-corpus honest signal
    if result.n_corpus_total == 0:
        findings.append({
            "type":               "corpus_empty",
            "note":               ("no historical outcomes yet — the learning corpus populates as "
                                    "recommendations close their 60-day horizons OR as Sprint 8 "
                                    "walk-forward generates historical closes. This is honest, not broken."),
            "next_step_hint":     "Sprint 8 walk-forward will generate historical closes at scale.",
        })
    else:
        # Model attribution — top alpha creators + destroyers
        creators = [m for m in result.model_attribution if m.net_alpha > 0][:3]
        destroyers = [m for m in result.model_attribution if m.net_alpha < 0][-3:]
        for m in creators:
            findings.append({
                "type":                "alpha_creator",
                "model_id":            m.key,
                "n_observations":      m.n_observations,
                "net_alpha":           m.net_alpha,
                "winner_frequency":    m.winner_frequency,
            })
        for m in destroyers:
            findings.append({
                "type":                "alpha_destroyer",
                "model_id":            m.key,
                "n_observations":      m.n_observations,
                "net_alpha":           m.net_alpha,
                "loser_frequency":     m.loser_frequency,
                "recommended_step":    "route to Sprint 10 Research Factory as deprecation candidate (operator approval required)",
            })

        # Top features by |net_alpha|
        for f in result.feature_attribution[:5]:
            findings.append({
                "type":                "top_feature_by_net_alpha",
                "feature":             f.key,
                "n_observations":      f.n_observations,
                "net_alpha":           f.net_alpha,
                "winner_frequency":    f.winner_frequency,
            })

        # Failure clusters — top 3
        for c in sorted(result.failure_clusters, key=lambda x: x.n_members, reverse=True)[:3]:
            findings.append({
                "type":                    "failure_cluster",
                "cluster_id":              c.cluster_id,
                "n_members":               c.n_members,
                "dominant_error_bucket":   c.dominant_error_bucket,
                "dominant_features":       c.dominant_features,
                "representative_tickers":  c.representative_tickers,
                "recommended_step":        c.recommended_step,
            })

    # Calibration health
    cal = result.calibration_curve
    if cal is not None:
        findings.append({
            "type":              "calibration_health",
            "method":            cal.method,
            "n_observations":    cal.n_observations,
            "calibration_error": cal.calibration_error,
            "note":              ("identity calibration — no adjustment applied"
                                    if cal.method == "identity"
                                    else "isotonic PAV — monotone fit to empirical win-rates"),
        })

    head = (f"corpus={result.n_corpus_total} · new_closed={result.n_new_closed} · "
             + (f"win_rate={result.win_rate * 100:.1f}%" if result.win_rate is not None else "win_rate=n/a")
             + f" · calibration={cal.method if cal else 'n/a'}")
    narr = (head + ".\n\n"
             "The Learning Engine's job is to close the feedback loop: match each closed "
             "recommendation to its outcome, compute feature/model attribution, cluster failures, "
             "and fit a calibration curve. It does NOT modify the recommendation engine. "
             "Every proposal (deprecation candidates, calibration updates) routes through the "
             "Promotion Gate for operator approval.")

    return AgentOutput(
        agent="learning_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={
            "n_corpus_total":    result.n_corpus_total,
            "n_winners":         result.n_winners,
            "n_losers":          result.n_losers,
            "win_rate":          result.win_rate,
            "calibration_method": cal.method if cal else "n/a",
        },
        citations=["backend/learning/engine.py", "configs/learning_config.yaml"],
        confidence=0.85 if result.n_corpus_total >= 30 else 0.50,
        caveats=[
            "corpus < 30 → attributions are directional, not statistically robust" if result.n_corpus_total < 30 else "",
            "SHAP/permutation importance deferred to Sprint 9",
            "descriptive only — never promotes",
        ],
        determinism="template",
    )
