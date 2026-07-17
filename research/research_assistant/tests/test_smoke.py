"""DEV026 smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from research_assistant.lib import loaders, templates                                   # noqa: E402
from research_assistant.compute import assistant                                         # noqa: E402


PASS, FAIL = 0, 0


def _check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def test_load_state():
    state = loaders.load_all()
    _check("state loads without error", state is not None)
    summary = loaders.state_summary(state)
    _check("state_summary returns dict", isinstance(summary, dict))


def test_explain_stock_synthetic():
    state = loaders.AegisState(
        company_context={
            "companies": [{
                "ticker": "TEST", "status": "computed",
                "score": 80, "confidence": 0.9, "classification": "Strong-Bullish",
                "hierarchy": {"sector_display": "Pharma", "sector_score": 75,
                                "sector_classification": "Bullish",
                                "industry_display": "Mid Cap Pharma",
                                "industry_score": 82, "industry_classification": "Strong-Bullish",
                                "global_posture": "Neutral", "global_score": 55},
                "rankings": {"overall_rank": 1, "sector_rank": 1, "sector_total": 15,
                              "industry_rank": 1, "industry_total": 6, "rs_rank": 3, "risk_rank": 5},
                "positive_drivers": [{"indicator": "norm.company.momentum", "value_0_100": 90}],
                "negative_drivers": [],
                "largest_strengths": [{"indicator": "norm.company.rs_industry", "value_0_100": 88}],
                "largest_risks": [],
            }]
        },
        recommendations={
            "recommendations": [{"ticker": "TEST", "recommendation": "Strong-Buy",
                                    "action": "NEW_POSITION",
                                    "reasons_for": ["high_score", "target_portfolio"],
                                    "reasons_against": [],
                                    "conviction_pct": 82,
                                    "entry_exit": {"latest_close": 100, "target_1": 110,
                                                    "stop_loss": 92}}]
        },
    )
    r = templates.explain_stock(state, "TEST")
    _check("explain_stock finds ticker", r.get("ticker") == "TEST")
    _check("explain_stock has narrative",
            "narrative" in r and len(r["narrative"]) > 20)
    _check("explain_stock returns recommendation",
            r["recommendation"] == "Strong-Buy")


def test_explain_stock_missing():
    state = loaders.AegisState(company_context={"companies": []})
    r = templates.explain_stock(state, "NONEXISTENT")
    _check("missing ticker -> not_found", r.get("status") == "not_found")


def test_compare():
    state = loaders.AegisState(
        company_context={"companies": [
            {"ticker": "A", "status": "computed", "score": 80, "confidence": 0.9,
              "classification": "Strong-Bullish", "hierarchy": {"sector_display": "S"},
              "rankings": {"overall_rank": 1}},
            {"ticker": "B", "status": "computed", "score": 60, "confidence": 0.7,
              "classification": "Bullish", "hierarchy": {"sector_display": "S"},
              "rankings": {"overall_rank": 10}},
        ]}
    )
    r = templates.compare_stocks(state, "A", "B")
    _check("compare produces both tickers",
            "A" in r["comparison"] and "B" in r["comparison"])
    _check("compare verdict favours A",
            "A" in r["verdict"] and "higher" in r["verdict"])


def test_sector_report():
    state = loaders.AegisState(
        sector_context={"sectors": [
            {"display_name": "Pharma", "status": "computed", "score": 75,
              "classification": "Bullish", "confidence": 0.85,
              "top_drivers": [{"indicator": "momentum"}],
              "top_detractors": []}]},
        industry_context={"industries": [
            {"display_name": "Pharma LC", "status": "computed",
              "parent_sector_display": "Pharma", "score": 80,
              "classification": "Strong-Bullish", "rotation": "Strong-Leader",
              "leadership_rank": 3}]},
        company_context={"companies": [
            {"ticker": "P1", "status": "computed", "score": 85, "classification": "Strong-Bullish",
              "hierarchy": {"sector_display": "Pharma", "industry_display": "Pharma LC"},
              "rankings": {"overall_rank": 5}}]},
    )
    r = templates.explain_sector(state, "Pharma")
    _check("sector report has score", r.get("sector_score") == 75)
    _check("sector report finds industries", len(r["industries"]) == 1)
    _check("sector report finds companies", len(r["top_10_companies"]) == 1)


def test_portfolio_report_no_data():
    state = loaders.AegisState()
    r = templates.portfolio_report(state)
    _check("no-portfolio -> status message",
            r.get("status") == "no_active_portfolio")


def test_executive_summary_empty():
    state = loaders.AegisState()
    r = templates.executive_summary(state)
    _check("executive_summary always has coverage dict",
            "coverage" in r and isinstance(r["coverage"], dict))
    _check("empty state -> no highlights",
            r.get("highlights") == [])


def test_investment_memo():
    state = loaders.AegisState(
        company_context={"companies": [{
            "ticker": "MEMO_TEST", "status": "computed", "score": 78,
            "confidence": 0.85, "classification": "Strong-Bullish",
            "hierarchy": {"sector_display": "IT", "sector_score": 70,
                            "sector_classification": "Bullish",
                            "industry_display": "IT Services",
                            "industry_score": 72, "industry_classification": "Bullish",
                            "global_posture": "Neutral", "global_score": 50},
            "rankings": {"overall_rank": 3, "sector_rank": 1, "sector_total": 8,
                          "industry_rank": 1, "industry_total": 5, "rs_rank": 2, "risk_rank": 4},
            "positive_drivers": [{"indicator": "momentum", "value_0_100": 85}],
            "negative_drivers": [], "largest_strengths": [{"indicator": "rs_nifty"}],
            "largest_risks": [],
        }]},
        recommendations={"recommendations": [{
            "ticker": "MEMO_TEST", "recommendation": "Strong-Buy",
            "conviction_pct": 75, "reasons_for": ["r1"], "reasons_against": [],
            "entry_exit": {"latest_close": 500, "target_1": 550, "stop_loss": 465,
                            "target_2": 600, "stop_loss_pct": -7}
        }]},
    )
    memo = templates.investment_memo(state, "MEMO_TEST")
    _check("memo has memo_type", memo.get("memo_type") == "investment_memo")
    _check("memo has thesis", "investment_thesis" in memo)
    _check("memo has risks", "risk_factors" in memo)
    _check("memo has entry_exit_plan", memo.get("entry_exit_plan") is not None)


def test_assistant_dispatcher():
    state = loaders.AegisState()
    r = assistant.answer(state, "executive_summary")
    _check("answer wraps with governance",
            r.get("governance", "").startswith("Deterministic"))
    _check("answer includes dev_version",
            r.get("dev_version") == "DEV026 v0.1")
    _check("answer echoes query_type",
            r.get("query_type") == "executive_summary")

    r = assistant.answer(state, "unknown_query")
    _check("unknown query returns status",
            r.get("status") == "unknown_query")


def test_determinism():
    state = loaders.AegisState(
        company_context={"companies": [{
            "ticker": "D", "status": "computed", "score": 70, "confidence": 0.7,
            "classification": "Bullish",
            "hierarchy": {"sector_display": "X", "sector_score": 60, "sector_classification": "Neutral",
                            "industry_display": "Y", "industry_score": 65, "industry_classification": "Bullish",
                            "global_posture": "Neutral"},
            "rankings": {"overall_rank": 5, "sector_rank": 2, "sector_total": 10,
                          "industry_rank": 1, "industry_total": 3, "rs_rank": 4, "risk_rank": 6},
            "positive_drivers": [], "negative_drivers": [],
            "largest_strengths": [], "largest_risks": [],
        }]}
    )
    r1 = templates.explain_stock(state, "D")
    r2 = templates.explain_stock(state, "D")
    # Only 'generated_utc' can differ between runs — remove and compare
    r1.pop("generated_utc", None)
    r2.pop("generated_utc", None)
    _check("explain_stock is deterministic (ex-timestamp)",
            r1 == r2)


def main() -> int:
    print("=" * 70)
    print("  DEV026 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_load_state(); print()
    test_explain_stock_synthetic(); print()
    test_explain_stock_missing(); print()
    test_compare(); print()
    test_sector_report(); print()
    test_portfolio_report_no_data(); print()
    test_executive_summary_empty(); print()
    test_investment_memo(); print()
    test_assistant_dispatcher(); print()
    test_determinism(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
