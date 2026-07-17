"""DEV024 monitoring engine.

Orchestrates: load portfolio → refresh values → compute metrics → detect drift
→ generate alerts → produce rebalance plan → attribute winners/losers.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from portfolio_monitor.lib import holdings as hd, alerts as al                        # noqa: E402
from company_intelligence.lib import company_catalog                                    # noqa: E402


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


# ── Sector/industry lookup from company catalog ──────────────────────────────

def _lookup_sector_industry(ticker: str) -> tuple[str, str]:
    try:
        c = company_catalog.by_ticker(ticker)
        return c.parent_sector_display, c.industry_display
    except KeyError:
        return "Unknown", "Unknown"


# ── Sector/industry exposure ─────────────────────────────────────────────────

def compute_exposures(portfolio: hd.Portfolio) -> dict:
    sector_ex: dict[str, float] = defaultdict(float)
    industry_ex: dict[str, float] = defaultdict(float)
    for pos in portfolio.positions:
        if pos.current_weight is None:
            continue
        sec, ind = _lookup_sector_industry(pos.ticker)
        sector_ex[sec] += pos.current_weight
        industry_ex[ind] += pos.current_weight

    return {
        "sector_exposure":   {k: round(v, 4) for k, v in
                              sorted(sector_ex.items(), key=lambda kv: kv[1], reverse=True)},
        "industry_exposure": {k: round(v, 4) for k, v in
                              sorted(industry_ex.items(), key=lambda kv: kv[1], reverse=True)},
        "cash_pct":          round((portfolio.cash / portfolio.total_portfolio_value * 100)
                                    if portfolio.total_portfolio_value > 0 else 0.0, 2),
    }


# ── Winner / loser attribution ───────────────────────────────────────────────

def compute_attribution(portfolio: hd.Portfolio) -> dict:
    contributions = []
    for pos in portfolio.positions:
        if pos.unrealised_pnl_abs is None or pos.current_weight is None:
            continue
        sec, ind = _lookup_sector_industry(pos.ticker)
        contributions.append({
            "ticker":              pos.ticker,
            "sector":              sec,
            "industry":            ind,
            "pnl_abs":             round(pos.unrealised_pnl_abs, 2),
            "pnl_pct":             round(pos.unrealised_pnl_pct or 0.0, 2),
            "current_weight":      round(pos.current_weight, 4),
            "contribution_to_portfolio_pct":
                round((pos.unrealised_pnl_abs / portfolio.total_invested_capital * 100)
                      if portfolio.total_invested_capital > 0 else 0.0, 3),
        })
    contributions.sort(key=lambda c: c["pnl_abs"], reverse=True)

    winners = [c for c in contributions if c["pnl_pct"] > 0][:5]
    losers = [c for c in contributions if c["pnl_pct"] <= 0][-5:]  # bottom (most negative)

    # Sector-level contribution
    sector_pnl: dict[str, dict] = defaultdict(lambda: {"pnl_abs": 0.0, "n": 0})
    for c in contributions:
        d = sector_pnl[c["sector"]]
        d["pnl_abs"] += c["pnl_abs"]
        d["n"] += 1
    sector_rows = [{"sector": k, "pnl_abs": round(v["pnl_abs"], 2),
                       "n_positions": v["n"]}
                     for k, v in sorted(sector_pnl.items(),
                                          key=lambda kv: kv[1]["pnl_abs"], reverse=True)]

    industry_pnl: dict[str, dict] = defaultdict(lambda: {"pnl_abs": 0.0, "n": 0})
    for c in contributions:
        d = industry_pnl[c["industry"]]
        d["pnl_abs"] += c["pnl_abs"]
        d["n"] += 1
    industry_rows = [{"industry": k, "pnl_abs": round(v["pnl_abs"], 2),
                       "n_positions": v["n"]}
                      for k, v in sorted(industry_pnl.items(),
                                            key=lambda kv: kv[1]["pnl_abs"], reverse=True)]

    return {
        "winners":              winners,
        "losers":               losers,
        "sector_contribution":  sector_rows,
        "industry_contribution": industry_rows,
    }


# ── Rebalance plan ───────────────────────────────────────────────────────────

def rebalance_plan(portfolio: hd.Portfolio,
                     recommendations_by_ticker: dict[str, dict] | None = None,
                     min_rebal_shares: int = 1,
                     min_rebal_value: float = 1000.0) -> list[dict]:
    """For each position, compute the exact shares to buy/sell to restore target.

    Also emits CLOSE actions when a Sell recommendation exists.
    """
    plan = []
    recommendations_by_ticker = recommendations_by_ticker or {}
    tpv = portfolio.total_portfolio_value

    for pos in portfolio.positions:
        if pos.latest_close is None:
            continue
        current_val = pos.current_value or 0.0
        target_val = pos.target_weight * tpv
        delta_val = target_val - current_val
        delta_shares = int(round(delta_val / pos.latest_close)) if pos.latest_close > 0 else 0

        # Check for sell/reduce recommendation from DEV023
        current_rec = recommendations_by_ticker.get(pos.ticker, {})
        rec_type = current_rec.get("recommendation")

        if rec_type in ("Sell",):
            plan.append({
                "ticker":       pos.ticker,
                "action":       "CLOSE_POSITION",
                "shares_delta": -pos.shares,
                "value_delta":  round(-current_val, 2),
                "reason":       "DEV023 Sell recommendation",
                "current_shares": pos.shares,
                "target_shares":  0,
                "priority":     1,
            })
            continue

        if rec_type == "Reduce":
            reduce_by = int(pos.shares * 0.5)
            plan.append({
                "ticker":       pos.ticker,
                "action":       "REDUCE_POSITION",
                "shares_delta": -reduce_by,
                "value_delta":  round(-reduce_by * pos.latest_close, 2),
                "reason":       "DEV023 Reduce recommendation — halving position",
                "current_shares": pos.shares,
                "target_shares":  pos.shares - reduce_by,
                "priority":     2,
            })
            continue

        if abs(delta_shares) < min_rebal_shares or abs(delta_val) < min_rebal_value:
            continue                            # Under threshold — no action

        if delta_shares > 0:
            action = "INCREASE_POSITION"
            reason = (f"Weight drifted below target: current {pos.current_weight*100:.2f}%, "
                       f"target {pos.target_weight*100:.2f}%")
            priority = 4
        else:
            action = "DECREASE_POSITION"
            reason = (f"Weight drifted above target: current {pos.current_weight*100:.2f}%, "
                       f"target {pos.target_weight*100:.2f}%")
            priority = 3

        plan.append({
            "ticker":       pos.ticker,
            "action":       action,
            "shares_delta": delta_shares,
            "value_delta":  round(delta_shares * pos.latest_close, 2),
            "reason":       reason,
            "current_shares": pos.shares,
            "target_shares":  pos.shares + delta_shares,
            "current_weight_pct": round((pos.current_weight or 0.0) * 100, 2),
            "target_weight_pct":  round(pos.target_weight * 100, 2),
            "priority":     priority,
        })

    plan.sort(key=lambda p: p["priority"])
    return plan


# ── Portfolio-level metrics ──────────────────────────────────────────────────

def compute_portfolio_health(portfolio: hd.Portfolio, exposures: dict, alerts: list[al.Alert]) -> dict:
    n_pos = len(portfolio.positions)
    n_computable = sum(1 for p in portfolio.positions if p.current_value is not None)

    # HHI
    if portfolio.total_portfolio_value > 0:
        hhi = sum((p.current_weight or 0) ** 2 for p in portfolio.positions)
        effective_n = 1.0 / hhi if hhi > 0 else 0
    else:
        hhi = 0.0
        effective_n = 0.0

    # Health score
    n_critical = sum(1 for a in alerts if a.severity == "CRITICAL")
    n_warning  = sum(1 for a in alerts if a.severity == "WARNING")
    health_score = max(0.0, 100.0 - n_critical * 10.0 - n_warning * 2.0)

    return {
        "portfolio_id":               portfolio.portfolio_id,
        "days_active":                portfolio.days_active,
        "total_portfolio_value":      round(portfolio.total_portfolio_value, 2),
        "total_equity_value":         round(portfolio.total_equity_value, 2),
        "cash":                       round(portfolio.cash, 2),
        "cash_pct":                   exposures["cash_pct"],
        "total_invested_capital":     round(portfolio.total_invested_capital, 2),
        "total_pnl_abs":              round(portfolio.total_pnl_abs, 2),
        "total_pnl_pct":              round(portfolio.total_pnl_pct, 2),
        "n_positions_total":          n_pos,
        "n_positions_computable":     n_computable,
        "stock_hhi":                  round(hhi, 4),
        "effective_n_stocks":         round(effective_n, 2),
        "top_sector":                 next(iter(exposures["sector_exposure"]), None),
        "top_sector_share":           list(exposures["sector_exposure"].values())[0]
                                       if exposures["sector_exposure"] else None,
        "n_alerts_critical":          n_critical,
        "n_alerts_warning":           n_warning,
        "n_alerts_info":              sum(1 for a in alerts if a.severity == "INFO"),
        "health_score":               round(health_score, 1),
    }


# ── Main orchestration ──────────────────────────────────────────────────────

def run(holdings_path: Path, verbose: bool = True) -> dict:
    portfolio = hd.load_holdings(holdings_path)
    if portfolio is None:
        return {"error": f"holdings file not found or invalid: {holdings_path}"}

    if verbose:
        print(f"  portfolio_id:      {portfolio.portfolio_id}")
        print(f"  positions loaded:  {len(portfolio.positions)}")

    # Refresh market values
    portfolio = hd.refresh_market_values(portfolio)
    if verbose:
        print(f"  total portfolio:   INR{portfolio.total_portfolio_value:,.0f}")
        print(f"  P&L:               INR{portfolio.total_pnl_abs:,.0f} ({portfolio.total_pnl_pct:+.2f}%)")

    # Exposures + attribution + health
    exposures = compute_exposures(portfolio)
    attribution = compute_attribution(portfolio)

    # Reload DEV023 recommendations for confidence-drop alerts + rebalance guidance
    recs_json = _load_json(REPORTS_DIR / "recommendations.json") or {}
    recs_by_ticker = {r["ticker"]: r for r in recs_json.get("recommendations", [])}

    alerts = al.scan(portfolio, recs_by_ticker)
    rebal = rebalance_plan(portfolio, recs_by_ticker)
    health = compute_portfolio_health(portfolio, exposures, alerts)

    return {
        "run_utc":        datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":       _git_sha(),
        "portfolio":      portfolio,
        "exposures":      exposures,
        "attribution":    attribution,
        "alerts":         alerts,
        "rebalance_plan": rebal,
        "health":         health,
    }
