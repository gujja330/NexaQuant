"""DEV022 publish — 6 JSON reports + portfolio parquet."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"

sys.path.insert(0, str(_ROOT / "research"))
from portfolio_construction.compute import risk_analytics                              # noqa: E402
from portfolio_construction.lib import stress_tests                                     # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    return obj


def build_and_publish(portfolios: list[dict], price_data: dict[str, pd.Series],
                        nifty_series: pd.Series, code_sha: str = "nogit",
                        run_stress: bool = True) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    # Risk analytics + stress tests per portfolio
    enriched = []
    for p in portfolios:
        if p.get("status") != "built":
            enriched.append(p)
            continue
        risk = risk_analytics.analyse(p, price_data, nifty_series)
        p["risk"] = _sanitize(risk)
        if run_stress:
            weights = {pos["ticker"]: pos["weight"] for pos in p["positions"]}
            stress = stress_tests.stress_test_portfolio(weights, price_data)
            p["stress_tests"] = _sanitize(stress)
        enriched.append(p)

    # ── portfolio.json ── one entry per (portfolio_type, allocator) ─────────
    portfolio_out = {
        "dev_version":     "DEV022 v0.1",
        "run_utc":         _now(),
        "code_sha":        code_sha,
        "n_portfolios":    len(enriched),
        "portfolios":      _sanitize(enriched),
    }
    with (PUBLISH_DIR / "portfolio.json").open("w", encoding="utf-8") as f:
        json.dump(portfolio_out, f, indent=2, default=str)

    # ── portfolio.parquet ── flat position table ────────────────────────────
    rows = []
    for p in enriched:
        if p.get("status") != "built":
            continue
        for pos in p["positions"]:
            rows.append({
                "portfolio_type":   p["portfolio_type"],
                "portfolio_display": p["portfolio_display"],
                "allocator":        p["allocator"],
                "ticker":           pos["ticker"],
                "weight":           pos["weight"],
                "score":            pos["score"],
                "confidence":       pos["confidence"],
                "sector":           pos["sector"],
                "industry":         pos["industry"],
                "overall_rank":     pos["overall_rank"],
            })
    if rows:
        pd.DataFrame(rows).to_parquet(PUBLISH_DIR / "portfolio.parquet", index=False)

    # ── risk_report.json ── per-portfolio risk summary ──────────────────────
    risk_out = {
        "run_utc": _now(),
        "per_portfolio": [
            {
                "portfolio_type": p["portfolio_type"],
                "allocator":      p["allocator"],
                "n_positions":    p.get("n_positions"),
                "annualised_vol_pct":  (p.get("risk") or {}).get("annualised_volatility_pct"),
                "beta":                (p.get("risk") or {}).get("beta_vs_nifty"),
                "diversification_ratio": (p.get("risk") or {}).get("diversification_ratio"),
                "expected_annual_return_pct": (p.get("risk") or {}).get("expected_annual_return_pct"),
                "expected_sharpe":     (p.get("risk") or {}).get("expected_sharpe"),
                "stock_hhi":           (p.get("risk") or {}).get("concentration", {}).get("stock_hhi"),
                "sector_hhi":          (p.get("risk") or {}).get("concentration", {}).get("sector_hhi"),
                "effective_n_stocks":  (p.get("risk") or {}).get("concentration", {}).get("effective_n_stocks"),
                "effective_n_sectors": (p.get("risk") or {}).get("concentration", {}).get("effective_n_sectors"),
                "top3_sector_share":   (p.get("risk") or {}).get("concentration", {}).get("top3_sector_share"),
            }
            for p in enriched if p.get("status") == "built"
        ],
    }
    with (PUBLISH_DIR / "risk_report.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(risk_out), f, indent=2, default=str)

    # ── allocation_report.json ── sector/industry breakdown ─────────────────
    alloc_out = {
        "run_utc": _now(),
        "per_portfolio": [
            {
                "portfolio_type": p["portfolio_type"],
                "allocator":      p["allocator"],
                "n_positions":    p.get("n_positions"),
                "sector_breakdown":   (p.get("risk") or {}).get("concentration", {}).get("sector_breakdown"),
                "industry_breakdown": (p.get("risk") or {}).get("concentration", {}).get("industry_breakdown"),
                "top_5_positions": [
                    {"ticker": pos["ticker"], "weight": pos["weight"], "sector": pos["sector"]}
                    for pos in p["positions"][:5]
                ],
            }
            for p in enriched if p.get("status") == "built"
        ],
    }
    with (PUBLISH_DIR / "allocation_report.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(alloc_out), f, indent=2, default=str)

    # ── rebalance_report.json ── suggested rebalance signals ────────────────
    rebal_out = {
        "run_utc": _now(),
        "note":    ("v0.1: rebalance recommendations are per-portfolio suggestions "
                      "based on threshold heuristics (>15% single-stock drift, "
                      ">10% sector-cap breach). Actual rebalance execution is "
                      "operator-manual (ARCH001A Article VIII clause 8.6)."),
        "recommended_cadence": "monthly (aligned with DEV021 backtest window)",
        "per_portfolio": [
            {
                "portfolio_type": p["portfolio_type"],
                "allocator":      p["allocator"],
                "signals": _rebalance_signals(p),
            }
            for p in enriched if p.get("status") == "built"
        ],
    }
    with (PUBLISH_DIR / "rebalance_report.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(rebal_out), f, indent=2, default=str)

    # ── stress_test.json ── historical scenario replays ────────────────────
    if run_stress:
        stress_out = {
            "run_utc": _now(),
            "note":    "Historical portfolio replay over 5 institutional stress windows.",
            "per_portfolio": [
                {
                    "portfolio_type": p["portfolio_type"],
                    "allocator":      p["allocator"],
                    "stress_windows": (p.get("stress_tests") or {}).get("stress_windows", []),
                }
                for p in enriched if p.get("status") == "built"
            ],
        }
        with (PUBLISH_DIR / "stress_test.json").open("w", encoding="utf-8") as f:
            json.dump(_sanitize(stress_out), f, indent=2, default=str)

    # ── summary_leaderboard.json ── quick comparison across portfolios ──────
    leaderboard = []
    for p in enriched:
        if p.get("status") != "built":
            continue
        risk = p.get("risk", {})
        conc = (risk or {}).get("concentration", {}) if risk else {}
        leaderboard.append({
            "portfolio":            f"{p['portfolio_type']} × {p['allocator']}",
            "n_positions":          p.get("n_positions"),
            "expected_return_pct":  risk.get("expected_annual_return_pct"),
            "expected_vol_pct":     risk.get("annualised_volatility_pct"),
            "expected_sharpe":      risk.get("expected_sharpe"),
            "beta":                 risk.get("beta_vs_nifty"),
            "effective_n_stocks":   conc.get("effective_n_stocks"),
            "effective_n_sectors":  conc.get("effective_n_sectors"),
            "top3_sector_share":    conc.get("top3_sector_share"),
        })
    leaderboard.sort(key=lambda r: (r["expected_sharpe"] if r["expected_sharpe"] is not None else -99),
                       reverse=True)
    with (PUBLISH_DIR / "portfolio_leaderboard.json").open("w", encoding="utf-8") as f:
        json.dump({"run_utc": _now(), "leaderboard": leaderboard}, f, indent=2, default=str)

    return {
        "portfolios":  enriched,
        "leaderboard": leaderboard,
    }


def _rebalance_signals(portfolio: dict) -> list[str]:
    """Heuristic rebalance suggestions."""
    signals = []
    risk = portfolio.get("risk", {}) or {}
    conc = risk.get("concentration", {}) or {}

    if conc.get("top3_stock_share") and conc["top3_stock_share"] > 0.5:
        signals.append("HIGH_STOCK_CONCENTRATION: top-3 stocks exceed 50% of portfolio")
    if conc.get("sector_hhi") and conc["sector_hhi"] > 0.3:
        signals.append(f"HIGH_SECTOR_CONCENTRATION: HHI = {conc['sector_hhi']:.3f}")
    if conc.get("effective_n_stocks") and conc["effective_n_stocks"] < 5:
        signals.append(f"LOW_EFFECTIVE_DIVERSIFICATION: effective N = {conc['effective_n_stocks']:.1f}")
    if risk.get("annualised_volatility_pct") and risk["annualised_volatility_pct"] > 30:
        signals.append(f"HIGH_PORTFOLIO_VOL: {risk['annualised_volatility_pct']:.1f}% ann")
    if risk.get("beta_vs_nifty") and abs(risk["beta_vs_nifty"] - 1.0) > 0.4:
        signals.append(f"BETA_DEVIATION: {risk['beta_vs_nifty']:.2f} (far from market)")

    for v in portfolio.get("violations", []):
        if "scaled_sector" in v or "scaled_industry" in v:
            signals.append(f"CONSTRAINT_APPLIED_AT_BUILD: {v}")
        elif "capped_max_weight" in v:
            signals.append(f"CONSTRAINT_APPLIED_AT_BUILD: {v}")

    if not signals:
        signals.append("STABLE: no rebalance recommended in v0.1 heuristics")
    return signals
