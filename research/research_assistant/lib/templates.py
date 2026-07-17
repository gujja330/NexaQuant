"""DEV026 template generators — turn AegisState + question into a memo/report.

Every function returns a dict with structured fields. Deterministic, grounded,
explainable per ARCH001A Article VIII clause 8.2.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .loaders import AegisState, find_company, find_recommendation, find_sector, find_industry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


# ─── Why a stock was recommended ─────────────────────────────────────────────

def explain_stock(state: AegisState, ticker: str) -> dict:
    company = find_company(state, ticker)
    if company is None:
        return {"ticker": ticker, "status": "not_found",
                "message": f"{ticker} not in company_context.json"}

    rec = find_recommendation(state, ticker) or {}
    hierarchy = company.get("hierarchy", {})
    rankings = company.get("rankings", {})

    result = {
        "generated_utc":   _now(),
        "ticker":          ticker,
        "recommendation":  rec.get("recommendation", "n/a"),
        "action":          rec.get("action"),
        "composite_score": company.get("score"),
        "confidence":      company.get("confidence"),
        "classification":  company.get("classification"),

        "hierarchy": {
            "global_posture":       hierarchy.get("global_posture"),
            "global_score":         hierarchy.get("global_score"),
            "sector":               hierarchy.get("sector_display"),
            "sector_score":         hierarchy.get("sector_score"),
            "sector_class":         hierarchy.get("sector_classification"),
            "industry":             hierarchy.get("industry_display"),
            "industry_score":       hierarchy.get("industry_score"),
            "industry_class":       hierarchy.get("industry_classification"),
        },

        "rankings": {
            "overall_rank":   rankings.get("overall_rank"),
            "sector_rank":    f"{rankings.get('sector_rank')}/{rankings.get('sector_total')}",
            "industry_rank":  f"{rankings.get('industry_rank')}/{rankings.get('industry_total')}",
            "rs_rank":        rankings.get("rs_rank"),
            "risk_rank":      rankings.get("risk_rank"),
        },

        "positive_drivers":  company.get("positive_drivers", [])[:5],
        "negative_drivers":  company.get("negative_drivers", []),
        "largest_strengths": company.get("largest_strengths", []),
        "largest_risks":     company.get("largest_risks", []),

        "entry_exit":        rec.get("entry_exit"),

        "reasons_for":       rec.get("reasons_for", []),
        "reasons_against":   rec.get("reasons_against", []),

        "narrative":         _stock_narrative(company, rec),
    }
    return result


def _stock_narrative(company: dict, rec: dict) -> str:
    """One-paragraph plain-English rationale."""
    h = company.get("hierarchy", {})
    ee = rec.get("entry_exit") or {}
    ticker = company.get("ticker", "?")
    rec_type = rec.get("recommendation", "n/a")
    score = company.get("score")
    conf = company.get("confidence")
    sec = h.get("sector_display", "n/a")
    sec_class = h.get("sector_classification", "n/a")
    ind = h.get("industry_display", "n/a")
    ind_class = h.get("industry_classification", "n/a")
    latest = ee.get("latest_close")
    t1 = ee.get("target_1")
    sl = ee.get("stop_loss")

    sec_score_str = f" with score {h.get('sector_score'):.1f}" if h.get("sector_score") else ""
    ind_score_str = f" with score {h.get('industry_score'):.1f}" if h.get("industry_score") else ""
    n = (f"{ticker} carries an AEGIS composite score of {score:.1f} with "
          f"confidence {conf:.2f}, classified as {company.get('classification')}. ")
    n += (f"Its parent sector ({sec}) is {sec_class}{sec_score_str}; "
           f"industry ({ind}) is {ind_class}{ind_score_str}. ")
    if rec_type not in ("n/a", None) and latest and t1 and sl:
        pct_to_target = (t1 / latest - 1) * 100
        pct_to_stop = (sl / latest - 1) * 100
        n += (f"DEV023 recommends {rec_type} with entry near INR {latest:.2f}, "
               f"target INR {t1:.2f} ({pct_to_target:+.1f}%), "
               f"stop INR {sl:.2f} ({pct_to_stop:+.1f}%). ")
    return n


# ─── Compare two companies ──────────────────────────────────────────────────

def compare_stocks(state: AegisState, ticker_a: str, ticker_b: str) -> dict:
    a = find_company(state, ticker_a)
    b = find_company(state, ticker_b)
    if a is None or b is None:
        return {"status": "not_found",
                "message": f"missing {ticker_a if a is None else ticker_b}"}

    rec_a = find_recommendation(state, ticker_a) or {}
    rec_b = find_recommendation(state, ticker_b) or {}

    def _row(c, r):
        h = c.get("hierarchy", {})
        return {
            "ticker":          c.get("ticker"),
            "score":           c.get("score"),
            "confidence":      c.get("confidence"),
            "classification":  c.get("classification"),
            "sector":          h.get("sector_display"),
            "sector_score":    h.get("sector_score"),
            "industry":        h.get("industry_display"),
            "industry_score":  h.get("industry_score"),
            "overall_rank":    c.get("rankings", {}).get("overall_rank"),
            "recommendation":  r.get("recommendation"),
            "conviction_pct":  r.get("conviction_pct"),
            "latest_close":    (r.get("entry_exit") or {}).get("latest_close"),
        }

    a_row, b_row = _row(a, rec_a), _row(b, rec_b)

    # Verdict
    if (a_row["score"] or 0) > (b_row["score"] or 0) + 5:
        verdict = f"{ticker_a} scores materially higher than {ticker_b}"
    elif (b_row["score"] or 0) > (a_row["score"] or 0) + 5:
        verdict = f"{ticker_b} scores materially higher than {ticker_a}"
    else:
        verdict = f"{ticker_a} and {ticker_b} score comparably"

    return {
        "generated_utc": _now(),
        "comparison": {ticker_a: a_row, ticker_b: b_row},
        "verdict":     verdict,
    }


# ─── Sector deep-dive ────────────────────────────────────────────────────────

def explain_sector(state: AegisState, sector_name: str) -> dict:
    sector = find_sector(state, sector_name)
    if sector is None:
        return {"status": "not_found", "sector": sector_name}

    # Constituent companies + industries within this sector
    industries = []
    if state.industry_context:
        for i in state.industry_context.get("industries", []):
            if (i.get("parent_sector_display", "").lower() == sector_name.lower()
                    and i.get("status") == "computed"):
                industries.append({
                    "industry":         i.get("display_name"),
                    "score":            i.get("score"),
                    "classification":   i.get("classification"),
                    "rotation":         i.get("rotation"),
                    "leadership_rank":  i.get("leadership_rank"),
                })

    companies = []
    if state.company_context:
        for c in state.company_context.get("companies", []):
            if (c.get("status") == "computed" and
                    (c.get("hierarchy", {}) or {}).get("sector_display", "").lower() ==
                    sector_name.lower()):
                companies.append({
                    "ticker":         c.get("ticker"),
                    "score":          c.get("score"),
                    "classification": c.get("classification"),
                    "industry":       c.get("hierarchy", {}).get("industry_display"),
                    "overall_rank":   c.get("rankings", {}).get("overall_rank"),
                })
    companies.sort(key=lambda x: x.get("score") or 0, reverse=True)

    return {
        "generated_utc":   _now(),
        "sector":          sector_name,
        "sector_score":    sector.get("score"),
        "classification":  sector.get("classification"),
        "confidence":      sector.get("confidence"),
        "allocation_pct":  sector.get("allocation_recommendation_pct"),
        "top_drivers":     sector.get("top_drivers", [])[:5],
        "top_detractors":  sector.get("top_detractors", []),
        "industries":      industries,
        "top_10_companies": companies[:10],
        "n_companies_in_sector": len(companies),
    }


# ─── Portfolio report ────────────────────────────────────────────────────────

def portfolio_report(state: AegisState) -> dict:
    if state.portfolio_monitor is None:
        return {"status": "no_active_portfolio",
                "message": "reports/portfolio_monitor.json missing — run DEV024"}

    portfolio = state.portfolio_monitor.get("portfolio", {})
    exposures = state.portfolio_monitor.get("exposures", {})
    health = state.portfolio_monitor.get("health", {})
    alerts_summary = (state.alerts or {}).get("summary", {})
    attribution = (state.performance_report or {}).get("attribution", {})
    rebal_plan = (state.rebalance_plan or {}).get("plan", [])

    return {
        "generated_utc":       _now(),
        "portfolio_id":        portfolio.get("portfolio_id"),
        "days_active":         portfolio.get("days_active"),
        "total_value":         portfolio.get("total_portfolio_value"),
        "invested":            portfolio.get("total_invested_capital"),
        "pnl_abs":             portfolio.get("total_pnl_abs"),
        "pnl_pct":             portfolio.get("total_pnl_pct"),
        "n_positions":         len(portfolio.get("positions", [])),
        "cash":                portfolio.get("cash"),
        "cash_pct":            exposures.get("cash_pct"),
        "sector_exposure":     exposures.get("sector_exposure"),
        "industry_exposure_top5": dict(list((exposures.get("industry_exposure") or {}).items())[:5]),
        "top_sector":          health.get("top_sector"),
        "top_sector_share":    health.get("top_sector_share"),
        "effective_n_stocks":  health.get("effective_n_stocks"),
        "health_score":        health.get("health_score"),
        "n_alerts_critical":   health.get("n_alerts_critical"),
        "n_alerts_warning":    health.get("n_alerts_warning"),
        "alerts_summary":      alerts_summary,
        "winners_top5":        attribution.get("winners", [])[:5],
        "losers_top5":         attribution.get("losers", [])[:5],
        "n_rebalance_actions": len(rebal_plan),
        "rebalance_top5":      rebal_plan[:5],
        "narrative":           _portfolio_narrative(portfolio, health, alerts_summary),
    }


def _portfolio_narrative(portfolio, health, alerts_summary) -> str:
    pnl_pct = portfolio.get("total_pnl_pct")
    n_pos = len(portfolio.get("positions", []))
    top_sec = health.get("top_sector") or "n/a"
    top_share = health.get("top_sector_share") or 0.0
    health_score = health.get("health_score") or 0

    n = (f"Portfolio {portfolio.get('portfolio_id')} currently holds {n_pos} positions "
          f"with a health score of {health_score:.0f}/100. ")
    if pnl_pct is not None:
        n += f"P&L stands at {pnl_pct:+.2f}%. "
    n += f"Largest sector exposure is {top_sec} at {top_share*100:.1f}%. "
    critical = alerts_summary.get("by_severity", {}).get("CRITICAL", 0)
    warning = alerts_summary.get("by_severity", {}).get("WARNING", 0)
    if critical:
        n += f"{critical} CRITICAL alert(s) require operator attention. "
    if warning:
        n += f"{warning} warning(s) noted. "
    if not critical and not warning:
        n += "No urgent alerts active. "
    return n


# ─── Executive summary ──────────────────────────────────────────────────────

def executive_summary(state: AegisState) -> dict:
    result = {
        "generated_utc": _now(),
        "coverage":      {},
        "highlights":    [],
    }

    # Global context
    if state.global_context:
        gr = state.global_context.get("composites", {}).get("global_risk", {})
        result["global"] = {
            "posture":       state.global_context.get("classifications", {}).get("global_posture", {}).get("label"),
            "risk_score":    gr.get("value_0_100"),
            "confidence":    gr.get("confidence"),
        }
        result["coverage"]["global"] = True

    # Sector
    if state.sector_context:
        p = state.sector_context.get("portfolio_level", {})
        result["sectors"] = {
            "n_computed":         p.get("sectors_computed"),
            "top3":               p.get("top3_sectors"),
            "bottom3":            p.get("bottom3_sectors"),
            "class_distribution": p.get("class_distribution"),
        }
        result["coverage"]["sectors"] = True

    # Companies
    if state.company_context:
        p = state.company_context.get("portfolio_level", {})
        result["companies"] = {
            "n_computed":         p.get("companies_computed"),
            "top_10":             p.get("top_10", [])[:5],
            "class_distribution": p.get("class_distribution"),
        }
        result["coverage"]["companies"] = True

    # Recommendations
    if state.recommendations:
        counts: dict[str, int] = {}
        for r in state.recommendations.get("recommendations", []):
            counts[r.get("recommendation", "?")] = counts.get(r.get("recommendation", "?"), 0) + 1
        result["recommendations_counts"] = counts
        result["coverage"]["recommendations"] = True

    # Portfolio
    if state.portfolio_monitor:
        p = state.portfolio_monitor.get("portfolio", {})
        h = state.portfolio_monitor.get("health", {})
        result["portfolio_snapshot"] = {
            "portfolio_id":    p.get("portfolio_id"),
            "pnl_pct":         p.get("total_pnl_pct"),
            "health_score":    h.get("health_score"),
            "n_positions":     len(p.get("positions", [])),
        }
        result["coverage"]["portfolio"] = True

    # Learning
    if state.learning_summary:
        a = state.learning_summary.get("aggregate", {})
        result["learning"] = {
            "trades_analysed":  a.get("n_trades"),
            "win_rate_pct":     a.get("overall_win_rate_pct"),
            "brier_score":      a.get("brier_score"),
            "ece":              a.get("expected_calibration_err"),
            "n_suggestions":    state.learning_summary.get("n_suggestions_generated"),
        }
        result["coverage"]["learning"] = True

    # Highlights (narrative)
    if state.recommendations and state.company_context:
        strong_buys = [r for r in state.recommendations.get("recommendations", [])
                        if r.get("recommendation") == "Strong-Buy"]
        if strong_buys:
            result["highlights"].append(
                f"{len(strong_buys)} Strong-Buy recommendation(s) — top pick "
                f"{strong_buys[0]['ticker']} (score {strong_buys[0]['score']:.1f})"
            )

    if state.improvement_suggestions:
        high_sev = [s for s in state.improvement_suggestions.get("suggestions", [])
                    if s.get("severity") == "HIGH"]
        if high_sev:
            result["highlights"].append(
                f"{len(high_sev)} HIGH-severity improvement suggestion(s) from DEV025"
            )

    return result


# ─── Investment memo ────────────────────────────────────────────────────────

def investment_memo(state: AegisState, ticker: str) -> dict:
    """Long-form memo combining company + recommendation + sector + industry."""
    stock = explain_stock(state, ticker)
    if stock.get("status") == "not_found":
        return stock

    sector_name = stock["hierarchy"].get("sector")
    industry_name = stock["hierarchy"].get("industry")
    sector = find_sector(state, sector_name) if sector_name else None
    industry = find_industry(state, industry_name) if industry_name else None

    memo = {
        "generated_utc":       _now(),
        "ticker":               ticker,
        "memo_type":            "investment_memo",
        "executive_summary":    stock.get("narrative"),
        "recommendation":       stock.get("recommendation"),
        "conviction_pct":       (find_recommendation(state, ticker) or {}).get("conviction_pct"),

        "investment_thesis": {
            "positive_drivers":  stock.get("positive_drivers", []),
            "strengths":         stock.get("largest_strengths", []),
            "supporting_reasons": stock.get("reasons_for", []),
        },
        "risk_factors": {
            "negative_drivers":  stock.get("negative_drivers", []),
            "risks":             stock.get("largest_risks", []),
            "counter_reasons":   stock.get("reasons_against", []),
        },
        "sector_context": {
            "sector":            sector_name,
            "sector_score":      sector.get("score") if sector else None,
            "sector_class":      sector.get("classification") if sector else None,
        },
        "industry_context": {
            "industry":          industry_name,
            "industry_score":    industry.get("score") if industry else None,
            "industry_class":    industry.get("classification") if industry else None,
            "rotation":          industry.get("rotation") if industry else None,
        },
        "entry_exit_plan":   stock.get("entry_exit"),
        "hierarchical_position": stock.get("hierarchy"),
        "peer_rankings":     stock.get("rankings"),
    }
    return memo
