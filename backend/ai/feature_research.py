"""AI Feature Research Agent v1.0 — deterministic hypothesis generator.

Reads the current snapshot + importance + drift + governance results.
Emits:
  - **hypotheses**: structured proposals for new candidate features, each
    with a formula, business rationale, and economic intuition (using
    the same governance shape the Feature Registry requires).
  - **failure_patterns**: recurring combinations that historically preceded
    losses (surfaced when learning corpus is available).
  - **experiment_recommendations**: what to run next (which candidate to
    backtest, which existing feature to deprecate).

**Contract:** the agent NEVER promotes a feature and NEVER emits a
recommendation. Everything it produces is a proposal for operator review.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.ai.base import AgentOutput
from backend.feature_intelligence.governance import GovernanceResult
from backend.feature_intelligence.importance import ImportanceResult

VERSION = "v1.0"


# ── Hypothesis templates (deterministic — no LLM) ────────────
_HYPOTHESES = [
    {
        "name": "global_stress_index",
        "formula": "z(macro_vix) + z(macro_move) - z(macro_dxy_change) - z(macro_wti_change)",
        "business_rationale": "When equity vol, bond vol, and dollar strength all rise while oil weakens, "
                               "risk-off dominates and equities discount future cashflows more heavily.",
        "economic_intuition": "Cross-asset stress composite — historically a leading indicator for equity drawdowns.",
        "dependencies": ("macro_vix", "macro_move", "macro_dxy", "macro_wti_oil"),
    },
    {
        "name": "institutional_fear_index",
        "formula": "z(insider_net_90d < 0) + z(news_sentiment < 0) + z(fii_net_5d < 0)",
        "business_rationale": "When insiders sell, sentiment is negative, and FIIs exit simultaneously, "
                               "institutional players have information the tape hasn't priced in.",
        "economic_intuition": "Composite of three information sources with different latencies — "
                               "concurrent negative signal is high-conviction.",
        "dependencies": ("insider_net_90d", "news_sentiment", "fii_net_5d"),
    },
    {
        "name": "momentum_confirmation",
        "formula": "return_20d_pct × (mi_breadth_above_20ma_pct > 60) × (rsi_14 in [50, 70])",
        "business_rationale": "Individual momentum matters more when it's happening with the market, "
                               "not against it, and when the stock isn't already overbought.",
        "economic_intuition": "Trend-following in confirming regimes has higher expected reward than "
                               "trend-following against the tape.",
        "dependencies": ("return_20d_pct", "mi_breadth_above_20ma_pct", "rsi_14"),
    },
    {
        "name": "quality_at_reasonable_price",
        "formula": "fund_quality_score × (1 / fund_trailing_pe) × (1 / fund_price_to_book)",
        "business_rationale": "Buffett's core investment logic: quality companies at reasonable valuations "
                               "outperform poor companies bought cheaply.",
        "economic_intuition": "GARP factor — decades of academic evidence supports quality-at-value premium.",
        "dependencies": ("fund_quality_score", "fund_trailing_pe", "fund_price_to_book"),
    },
    {
        "name": "post_earnings_drift_setup",
        "formula": "(earn_last_surprise_pct > 5) × (0 < earn_days_to_next < 90) × return_5d_pct",
        "business_rationale": "PEAD is one of the most durable market anomalies — surprises trigger "
                               "gradual re-pricing over weeks, not seconds.",
        "economic_intuition": "Anchoring bias + slow analyst updates = predictable drift in the direction "
                               "of the surprise.",
        "dependencies": ("earn_last_surprise_pct", "earn_days_to_next", "return_5d_pct"),
    },
]


def run(df: pd.DataFrame | None,
         governance: GovernanceResult | None,
         importance: ImportanceResult | None,
         market_name: str,
         asof: date | None = None,
         top_k: int = 5) -> AgentOutput:
    findings: list[dict] = []
    citations = ["backend/feature_intelligence", "backend/feature_store/feature_registry"]

    # ── Hypotheses: propose top-k candidate features from the template bank
    for i, h in enumerate(_HYPOTHESES[:top_k]):
        # Check dependency coverage before proposing
        if df is not None:
            deps_present = sum(1 for d in h["dependencies"] if d in df.columns)
        else:
            deps_present = 0
        findings.append({
            "type":            "hypothesis",
            "candidate_name":  h["name"],
            "formula":         h["formula"],
            "business_rationale": h["business_rationale"],
            "economic_intuition": h["economic_intuition"],
            "dependencies":    list(h["dependencies"]),
            "deps_present":    deps_present,
            "deps_total":      len(h["dependencies"]),
            "readiness":       "READY" if deps_present == len(h["dependencies"]) else "MISSING_DEPS",
        })

    # ── Governance recommendations
    if governance is not None:
        if governance.missing_rationale:
            findings.append({
                "type":     "governance_action",
                "recommended_step": "fill_business_rationale",
                "affected": governance.missing_rationale[:20],
                "count":    len(governance.missing_rationale),
                "note":     ("Features without business rationale are more prone to spurious selection. "
                             "Fill these to reduce overfitting risk."),
            })
        if governance.missing_intuition:
            findings.append({
                "type":     "governance_action",
                "recommended_step": "fill_economic_intuition",
                "affected": governance.missing_intuition[:20],
                "count":    len(governance.missing_intuition),
            })

    # ── Importance-based deprecation candidates
    if importance is not None:
        low_imp = []
        for row in importance.per_feature:
            disp = row.get("dispersion") or 0
            uniq = row.get("uniqueness") or 1.0
            score = disp * uniq
            if score < 0.001:
                low_imp.append((row["feature"], round(score, 6)))
        low_imp.sort(key=lambda x: x[1])
        if low_imp:
            findings.append({
                "type":     "deprecation_candidates",
                "recommended_step": "review_for_deprecation",
                "affected": [n for n, _ in low_imp[:15]],
                "count":    len(low_imp),
                "note":     ("Low dispersion × low uniqueness = redundant. Consider marking these "
                             "features EXPERIMENTAL and testing whether removing them hurts walk-forward."),
            })

    ready_h = sum(1 for f in findings if f.get("type") == "hypothesis" and f.get("readiness") == "READY")
    head = (f"{ready_h}/{top_k} feature hypotheses ready to backtest · "
             f"{len([f for f in findings if f.get('type') == 'governance_action'])} governance actions · "
             f"{len([f for f in findings if f.get('type') == 'deprecation_candidates'])} deprecation batches")
    narr = (
        head + ".\n\n"
        "The AI Research Agent proposes candidate features — it does NOT promote them. "
        "Each hypothesis carries a formula + business rationale + economic intuition, matching the "
        "governance schema. Route each accepted candidate through: backtest → walk-forward → "
        "statistical validation → promotion gate → active feature set.\n\n"
        "Note: this template bank is deterministic. A later swap to an LLM-driven hypothesis "
        "generator can plug in with the same output shape — see backend/ai/base.py `determinism` field."
    )

    return AgentOutput(
        agent="feature_research", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={"n_hypotheses": len(_HYPOTHESES),
                    "n_governance_gaps":
                        (len(governance.missing_rationale) if governance else 0) +
                        (len(governance.missing_intuition) if governance else 0)},
        citations=citations,
        confidence=0.8,
        caveats=[
            "hypotheses are proposals only — approval required via promotion_gate",
            "template bank; LLM-driven generation deferred",
        ],
        determinism="template",
    )
