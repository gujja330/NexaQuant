"""DEV023 recommendation engine.

For every AEGIS-universe ticker:
  1. Load DEV020 company_context row
  2. Look up DEV019 industry + DEV018 sector + DEV017 global context
  3. Determine if ticker is in any DEV022 target portfolio
  4. Load current holdings (optional)
  5. Apply decision rules → recommendation type + action
  6. Compute entry/exit levels
  7. Build rationale
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from recommendations.lib import decisions, entry_exit                             # noqa: E402


REPORTS_DIR = _ROOT / "reports"
CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.load(path.open("r", encoding="utf-8"))
    except Exception:
        return None


def load_holdings(holdings_path: Path | None) -> dict[str, dict]:
    """Load current holdings if provided. Structure: {ticker: {shares, avg_cost}}."""
    if holdings_path is None or not holdings_path.exists():
        return {}
    try:
        data = json.load(holdings_path.open("r", encoding="utf-8"))
        return {h["ticker"]: h for h in data.get("holdings", [])}
    except Exception:
        return {}


def load_ticker_close(ticker: str) -> pd.Series | None:
    parq = CONSTITUENT_PARQ_DIR / f"{ticker}_D1.parquet"
    if not parq.exists():
        return None
    try:
        df = pd.read_parquet(parq)
        if df.empty or "close" not in df.columns:
            return None
        return df["close"].dropna()
    except Exception:
        return None


def _extract_target_portfolios(portfolio_bundle: dict | None,
                                  min_expected_sharpe: float = 1.5) -> dict[str, list[str]]:
    """Return ticker → list of portfolio_key that include this ticker.

    Filters to portfolios with expected Sharpe above the threshold (i.e. only
    high-quality target portfolios count as 'in target').
    """
    result: dict[str, list[str]] = defaultdict(list)
    if not portfolio_bundle:
        return result
    portfolios = portfolio_bundle.get("portfolios", [])
    for p in portfolios:
        if p.get("status") != "built":
            continue
        risk = p.get("risk") or {}
        exp_sharpe = risk.get("expected_sharpe")
        if exp_sharpe is None or exp_sharpe < min_expected_sharpe:
            continue
        pkey = f"{p['portfolio_type']}×{p['allocator']}"
        for pos in p.get("positions", []):
            result[pos["ticker"]].append(pkey)
    return dict(result)


def _lookup_from_hierarchy(company: dict) -> dict:
    """Extract flat lookup fields from a company row."""
    h = company.get("hierarchy", {})
    r = company.get("rankings", {})
    return {
        "ticker":                  company["ticker"],
        "company_score":           company["score"],
        "classification":          company["classification"],
        "confidence":              company["confidence"],
        "industry_score":          h.get("industry_score"),
        "industry_classification": h.get("industry_classification"),
        "industry_display":        h.get("industry_display"),
        "sector_score":            h.get("sector_score"),
        "sector_classification":   h.get("sector_classification"),
        "sector_display":          h.get("sector_display"),
        "global_posture":          h.get("global_posture"),
        "global_score":            h.get("global_score"),
        "overall_rank":            r.get("overall_rank"),
        "sector_rank":             r.get("sector_rank"),
        "industry_rank":           r.get("industry_rank"),
    }


def _current_position_metadata(spec: dict, holdings: dict[str, dict],
                                 latest_close: float | None) -> dict:
    """Enrich decision input with current-position metadata."""
    ticker = spec["ticker"]
    if ticker not in holdings:
        return {"currently_held": False}
    h = holdings[ticker]
    avg_cost = h.get("avg_cost")
    pnl_pct = None
    if avg_cost and latest_close:
        pnl_pct = (latest_close / avg_cost - 1) * 100
    return {
        "currently_held":     True,
        "current_weight":     h.get("current_weight"),
        "avg_cost":           avg_cost,
        "latest_close":       latest_close,
        "unrealised_pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
    }


# ─── Main orchestration ─────────────────────────────────────────────────────

def run(holdings_path: Path | None = None,
         min_target_sharpe: float = 1.5,
         verbose: bool = True) -> dict:
    """Produce recommendations for every AEGIS-universe ticker."""
    company_ctx = _load_json(REPORTS_DIR / "company_context.json")
    if not company_ctx:
        return {"error": "reports/company_context.json missing — run DEV020 first"}
    portfolio_ctx = _load_json(REPORTS_DIR / "portfolio.json")
    risk_ctx = _load_json(REPORTS_DIR / "risk_report.json")
    stress_ctx = _load_json(REPORTS_DIR / "stress_test.json")
    holdings = load_holdings(holdings_path)

    if verbose:
        print(f"  DEV020 companies:       "
                f"{sum(1 for c in company_ctx.get('companies', []) if c.get('status') == 'computed')}")
        print(f"  DEV022 portfolios:      "
                f"{len(portfolio_ctx.get('portfolios', [])) if portfolio_ctx else 0}")
        print(f"  Current holdings:       {len(holdings)}")
        print(f"  Min target Sharpe:      {min_target_sharpe}")

    target_portfolios_by_ticker = _extract_target_portfolios(portfolio_ctx, min_target_sharpe)
    if verbose:
        n_tickers_in_top = len(target_portfolios_by_ticker)
        print(f"  Tickers in high-Sharpe target portfolios: {n_tickers_in_top}")

    all_recommendations = []
    now_utc = datetime.now(timezone.utc).isoformat() + "Z"

    computed_companies = [c for c in company_ctx.get("companies", []) if c.get("status") == "computed"]

    for company in computed_companies:
        ticker = company["ticker"]
        base = _lookup_from_hierarchy(company)
        close_series = load_ticker_close(ticker)
        latest = float(close_series.iloc[-1]) if close_series is not None and len(close_series) > 0 else None

        pos_meta = _current_position_metadata(base, holdings, latest)

        dinp = decisions.DecisionInput(
            ticker=ticker,
            company_score=base["company_score"],
            classification=base["classification"],
            confidence=base["confidence"],
            industry_score=base["industry_score"],
            industry_classification=base["industry_classification"],
            sector_score=base["sector_score"],
            sector_classification=base["sector_classification"],
            global_posture=base["global_posture"],
            in_target_portfolios=target_portfolios_by_ticker.get(ticker, []),
            overall_rank=base["overall_rank"],
            **pos_meta,
        )

        decision = decisions.decide(dinp)

        # Entry/exit levels
        levels = None
        if close_series is not None and decision.recommendation not in (
                decisions.RecType.AVOID, decisions.RecType.SELL,
                decisions.RecType.REDUCE, decisions.RecType.HOLD):
            levels = entry_exit.compute(close_series, decision.recommendation.value)

        rec_row = {
            "ticker":                  ticker,
            "recommendation":          decision.recommendation.value,
            "action":                  decision.action.value,
            "composite_decision_score": round(decision.composite_decision_score, 2),
            "conviction_pct":          decision.conviction_pct,
            "confidence":              base["confidence"],

            "score":                   base["company_score"],
            "classification":          base["classification"],
            "sector":                  base["sector_display"],
            "sector_score":            base["sector_score"],
            "sector_classification":   base["sector_classification"],
            "industry":                base["industry_display"],
            "industry_score":          base["industry_score"],
            "industry_classification": base["industry_classification"],
            "global_posture":          base["global_posture"],
            "global_score":            base["global_score"],

            "overall_rank":            base["overall_rank"],
            "sector_rank":             base["sector_rank"],
            "industry_rank":           base["industry_rank"],

            "in_target_portfolios":    target_portfolios_by_ticker.get(ticker, []),
            "currently_held":          pos_meta.get("currently_held", False),
            "current_weight":          pos_meta.get("current_weight"),
            "unrealised_pnl_pct":      pos_meta.get("unrealised_pnl_pct"),

            "reasons_for":             decision.reasons_for,
            "reasons_against":         decision.reasons_against,

            "entry_exit":              asdict(levels) if levels else None,
        }
        all_recommendations.append(rec_row)

    # Sort by recommendation rank (Strong-Buy top, Sell/Avoid bottom) then by CDS desc
    rec_order = {
        "Strong-Buy": 0, "Buy": 1, "Accumulate": 2, "Hold": 3, "Watchlist": 4,
        "Reduce": 5, "Sell": 6, "Avoid": 7,
    }
    all_recommendations.sort(
        key=lambda r: (rec_order.get(r["recommendation"], 99),
                         -r["composite_decision_score"]))

    if verbose:
        counts = defaultdict(int)
        for r in all_recommendations:
            counts[r["recommendation"]] += 1
        print(f"  Recommendation counts:  {dict(counts)}")

    return {
        "run_utc":                   now_utc,
        "code_sha":                  _git_sha(),
        "n_companies_evaluated":     len(all_recommendations),
        "n_currently_held":          len(holdings),
        "n_in_target_portfolios":    len(target_portfolios_by_ticker),
        "min_target_sharpe":         min_target_sharpe,
        "recommendations":           all_recommendations,
    }
