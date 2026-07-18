"""Adaptive Rec Engine v2.1 · Fusion smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from adaptive_rec_v2.lib import dimensions, fusion, conflicts                          # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _sample_rec():
    return {
        "ticker": "AAA",
        "sector": "Pharma",
        "industry": "Pharma-Mid",
        "recommendation": "Strong-Buy",
        "score": 85.0,
        "sector_score": 82.0,
        "industry_score": 84.0,
        "global_score": 55.0,
        "composite_decision_score": 90.0,
        "confidence": 0.90,
        "in_target_portfolios": ["top_10", "top_20", "aggressive", "balanced", "quality"],
    }


def _sample_ctx():
    return {
        "learning": pd.DataFrame({
            "ticker": ["AAA"] * 10 + ["BBB"] * 5,
            "sector": ["Pharma"] * 15,
            "industry": ["Pharma-Mid"] * 15,
            "is_winner":  [1]*8 + [0]*2 + [1]*3 + [0]*2,
            "return_pct": [0.06]*8 + [-0.02]*2 + [0.04]*3 + [-0.03]*2,
        }),
        "validation": {"reconciliation": {"n": 10, "within_5pp_tolerance": True},
                        "metric_drift": {"flag": "stable"}},
        "risk": {"sizing": [{"ticker": "AAA", "target_weight": 0.075,
                                "verdict": "PASS"}],
                  "portfolio_risk": {"verdict": "PASS"}},
        "entity_network": {"nodes": [{"id": "Company:AAA", "influence": 0.008,
                                          "degree_centrality": 0.02}]},
        "dna_feedback": {"priors_all": [{"ticker": "AAA", "hist_evidence": True,
                                             "prior_win_rate": 0.80, "prior_expectancy": 0.05,
                                             "n_historical": 10}]},
        "calibration": {"raw_metrics": {"ece": 0.287},
                          "calibrated_metrics": {"ece": 0.002}},
        "rec_paths": {"paths": [{"ticker": "AAA", "found": True,
                                     "primary_path": [{}, {}, {}, {}],
                                     "champion": {"label": "top_5_ew"},
                                     "outcome": {"label": "winner", "win_rate": 0.8},
                                     "signals": [{}, {}, {}, {}]}]},
    }


def test_dimensions_returns_10_scores():
    dims = dimensions.score_all_dimensions(_sample_rec(), _sample_ctx())
    _check("returns 10 dimension entries", len(dims) == 10)
    names = {d.name for d in dims}
    expected = {"research", "historical", "validation", "risk", "portfolio_fit",
                 "knowledge_graph", "dna", "calibration", "learning", "explainability"}
    _check("all 10 dimensions named", names == expected)


def test_dimensions_deterministic():
    rec = _sample_rec()
    ctx = _sample_ctx()
    d1 = dimensions.score_all_dimensions(rec, ctx)
    d2 = dimensions.score_all_dimensions(rec, ctx)
    _check("same inputs -> same scores",
            [d.score for d in d1] == [d.score for d in d2])


def test_dimensions_bounded():
    dims = dimensions.score_all_dimensions(_sample_rec(), _sample_ctx())
    for d in dims:
        if d.score is None:
            continue
        _check(f"{d.name} score in [0, 100]", 0 <= d.score <= 100,
                detail=f"got {d.score}")


def test_dimensions_graceful_no_context():
    dims = dimensions.score_all_dimensions(_sample_rec(), {})
    for d in dims:
        if d.score is not None:
            _check(f"{d.name} bounded even with no ctx", 0 <= d.score <= 100)


def test_fusion_produces_score_and_decision():
    dims = dimensions.score_all_dimensions(_sample_rec(), _sample_ctx())
    fused = fusion.fuse(dims)
    _check("intelligence_score in [0, 100]",
            0 <= (fused["intelligence_score"] or 0) <= 100)
    _check("decision is a known label",
            fused["decision"] in ("Strong-Buy", "Buy", "Hold", "Reduce", "Avoid",
                                     "INSUFFICIENT_EVIDENCE"))
    _check("contributions sum ~ score",
            abs(sum(c["contribution"] for c in fused["contributions"]) -
                fused["intelligence_score"]) < 0.5)


def test_fusion_missing_dimensions_ok():
    # Simulate all dims None
    dims = [dimensions.DimensionScore(f"dim{i}", None, "", "test", 0.1) for i in range(10)]
    fused = fusion.fuse(dims)
    _check("all None -> INSUFFICIENT_EVIDENCE decision",
            fused["decision"] == "INSUFFICIENT_EVIDENCE")


def test_conflicts_fires_research_high_risk_low():
    rec = {"ticker": "AAA", "recommendation": "Buy"}
    dims = [
        dimensions.DimensionScore("research", 85.0, "", "", 0.15),
        dimensions.DimensionScore("risk",     20.0, "", "", 0.15),
    ]
    fused = fusion.fuse(dims + [dimensions.DimensionScore(f"d{i}", None, "", "", 0.05)
                                    for i in range(8)])
    cs = conflicts.detect_conflicts(rec, dims, fused)
    _check("research_high_risk_low fires",
            any(c["rule"] == "research_high_risk_low" for c in cs))
    _check("severity is CRITICAL",
            any(c["severity"] == "CRITICAL" and c["rule"] == "research_high_risk_low" for c in cs))


def test_conflicts_fires_raw_buy_fusion_sell():
    rec = {"ticker": "AAA", "recommendation": "Strong-Buy"}
    dims = [dimensions.DimensionScore(f"d{i}", 10.0, "", "", 0.1) for i in range(10)]
    fused = fusion.fuse(dims)
    _check("with dims=10 fusion decision is Avoid",
            fused["decision"] == "Avoid")
    cs = conflicts.detect_conflicts(rec, dims, fused)
    _check("raw_buy_fusion_sell fires when raw=Strong-Buy but fusion=Avoid",
            any(c["rule"] == "raw_buy_fusion_sell" for c in cs))


def test_conflicts_wide_spread():
    rec = {"ticker": "AAA", "recommendation": "Buy"}
    dims = [dimensions.DimensionScore("a", 95.0, "", "", 0.1),
             dimensions.DimensionScore("b", 45.0, "", "", 0.1)]
    fused = fusion.fuse(dims + [dimensions.DimensionScore(f"d{i}", None, "", "", 0.05)
                                    for i in range(8)])
    cs = conflicts.detect_conflicts(rec, dims, fused)
    _check("wide_dimension_spread fires",
            any(c["rule"] == "wide_dimension_spread" for c in cs))


def test_aggregate_conflicts():
    all_conflicts = {
        "AAA": [{"severity": "CRITICAL", "rule": "r1", "detail": "x"}],
        "BBB": [{"severity": "MEDIUM", "rule": "r2", "detail": "y"}],
        "CCC": [{"severity": "CRITICAL", "rule": "r1", "detail": "z"}],
    }
    agg = conflicts.aggregate_conflicts(all_conflicts)
    _check("aggregate counts 2 critical", agg["n_critical"] == 2)
    _check("aggregate counts 1 medium",   agg["n_medium"] == 1)
    _check("by_rule counts r1 twice",     agg["by_rule"].get("r1") == 2)
    _check("2 tickers with critical",     agg["n_tickers_with_critical"] == 2)


def test_why_this_and_why_not_stronger():
    dims = [dimensions.DimensionScore("a", 90.0, "high", "", 0.1),
             dimensions.DimensionScore("b", 20.0, "low", "", 0.1),
             dimensions.DimensionScore("c", 60.0, "mid", "", 0.1)]
    why = fusion.why_this_recommendation(dims)
    lower = fusion.why_not_stronger(dims)
    _check("why_this top is highest",  why[0]["name"] == "a")
    _check("why_not_stronger top is lowest", lower[0]["name"] == "b")


def main() -> int:
    print("=" * 72); print("  ADAPTIVE REC v2.1 · FUSION SMOKE TESTS"); print("=" * 72)
    test_dimensions_returns_10_scores(); print()
    test_dimensions_deterministic(); print()
    test_dimensions_bounded(); print()
    test_dimensions_graceful_no_context(); print()
    test_fusion_produces_score_and_decision(); print()
    test_fusion_missing_dimensions_ok(); print()
    test_conflicts_fires_research_high_risk_low(); print()
    test_conflicts_fires_raw_buy_fusion_sell(); print()
    test_conflicts_wide_spread(); print()
    test_aggregate_conflicts(); print()
    test_why_this_and_why_not_stronger(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
