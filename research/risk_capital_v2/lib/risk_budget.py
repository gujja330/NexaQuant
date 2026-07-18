"""Risk & Capital v2.0 · dynamic risk budget.

Given the current portfolio target weights and per-ticker volatility,
compute:
  - contribution to variance per position
  - sector-level risk contribution
  - portfolio-level VaR / CVaR (parametric normal, deterministic)
  - budget utilisation vs declared per-sector + per-position budgets

Every number carries an explanation. Every budget breach fires an
advisory alert that names the specific budget + position + margin."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


# Declared budgets (transparent, tenant-generic)
BUDGET_TOTAL_VAR_ANNUAL   = 0.20     # 20% annualised portfolio vol ceiling
BUDGET_PER_POSITION_VAR   = 0.05     # 5% variance contribution per single name
BUDGET_PER_SECTOR_VAR     = 0.30     # 30% aggregate variance contribution per sector
VAR_CONFIDENCE            = 0.95     # 95% VaR
Z_95                       = 1.6449   # 95% z-score
Z_99                       = 2.3263


@dataclass
class RiskAlert:
    kind:     str
    entity:   str
    detail:   str
    severity: str


@dataclass
class RiskDecision:
    portfolio_vol_annual: float
    var_95:               float
    var_99:               float
    cvar_95:              float
    per_position:         list[dict]
    per_sector:           list[dict]
    budget_utilisation:   dict
    alerts:               list[dict]
    verdict:              str


def _annualised_vol_series(returns: dict[str, float]) -> dict[str, float]:
    """Placeholder — annualised vol per ticker. Callers provide it directly."""
    return returns


def compute_risk(weights: dict[str, float],
                    ann_vol_by_ticker: dict[str, float],
                    sector_by_ticker: dict[str, str] | None = None,
                    correlations: np.ndarray | None = None) -> RiskDecision:
    """Compute portfolio risk with per-position + per-sector attribution.

    weights:            {ticker: weight}. Should sum to <= 1.0.
    ann_vol_by_ticker:  {ticker: annualised volatility}.
    sector_by_ticker:   {ticker: sector_name}. Optional but recommended.
    correlations:       Full correlation matrix (ordered by sorted tickers).
                         If None, assumes 0.30 average correlation (conservative)."""
    tickers = sorted(weights.keys())
    n = len(tickers)
    if n == 0:
        return RiskDecision(0.0, 0.0, 0.0, 0.0, [], [], {}, [], "empty portfolio")

    w = np.array([weights[t] for t in tickers], dtype=float)
    sigma = np.array([ann_vol_by_ticker.get(t, 0.30) for t in tickers], dtype=float)

    # Correlation matrix
    if correlations is None:
        rho = np.full((n, n), 0.30)
        np.fill_diagonal(rho, 1.0)
    else:
        rho = correlations.copy()
        np.fill_diagonal(rho, 1.0)

    # Portfolio variance
    cov = (sigma.reshape(-1, 1) * sigma.reshape(1, -1)) * rho
    port_var = float(w @ cov @ w)
    port_vol = float(np.sqrt(max(port_var, 0)))

    # Per-position risk contribution = w_i * (Σw)_i / port_var
    if port_var > 0:
        marginal = cov @ w
        contrib = (w * marginal) / port_var
    else:
        contrib = np.zeros(n)

    per_position = []
    for i, t in enumerate(tickers):
        per_position.append({
            "ticker":               t,
            "weight":               round(float(w[i]), 5),
            "annualised_vol":       round(float(sigma[i]), 4),
            "var_contribution":     round(float(contrib[i]), 4),
            "sector":               (sector_by_ticker or {}).get(t),
            "budget_utilisation":   round(float(contrib[i]) / BUDGET_PER_POSITION_VAR, 4)
                                     if BUDGET_PER_POSITION_VAR else None,
        })

    # Per-sector aggregation
    per_sector = []
    if sector_by_ticker:
        sec_agg = {}
        for i, t in enumerate(tickers):
            s = sector_by_ticker.get(t, "Unknown")
            sec_agg.setdefault(s, 0.0)
            sec_agg[s] += float(contrib[i])
        for s, c in sorted(sec_agg.items(), key=lambda kv: -kv[1]):
            per_sector.append({
                "sector":              s,
                "var_contribution":    round(c, 4),
                "budget_utilisation":  round(c / BUDGET_PER_SECTOR_VAR, 4),
            })

    var_95  = Z_95 * port_vol
    var_99  = Z_99 * port_vol
    cvar_95 = (np.exp(-Z_95**2 / 2) / (np.sqrt(2 * np.pi) * (1 - VAR_CONFIDENCE))) * port_vol

    # Budget utilisation
    total_util = port_vol / BUDGET_TOTAL_VAR_ANNUAL if BUDGET_TOTAL_VAR_ANNUAL else None
    budget_utilisation = {
        "total_portfolio_vol":        round(port_vol, 4),
        "budget_total_vol":           BUDGET_TOTAL_VAR_ANNUAL,
        "total_budget_utilisation":   round(total_util, 4) if total_util is not None else None,
        "per_position_budget":        BUDGET_PER_POSITION_VAR,
        "per_sector_budget":          BUDGET_PER_SECTOR_VAR,
    }

    # Alerts
    alerts = []
    if total_util is not None and total_util > 1.0:
        alerts.append({
            "kind":    "TOTAL_VOL_BUDGET_BREACH",
            "entity":  "portfolio",
            "detail":  f"portfolio vol {port_vol:.4f} exceeds budget {BUDGET_TOTAL_VAR_ANNUAL:.2f}",
            "severity": "HIGH",
        })
    for row in per_position:
        if row["budget_utilisation"] and row["budget_utilisation"] > 1.0:
            alerts.append({
                "kind":    "POSITION_VAR_BUDGET_BREACH",
                "entity":  row["ticker"],
                "detail":  f"{row['ticker']} contributes {row['var_contribution']:.4f} "
                            f"exceeding per-position budget {BUDGET_PER_POSITION_VAR}",
                "severity": "MEDIUM",
            })
    for row in per_sector:
        if row["budget_utilisation"] > 1.0:
            alerts.append({
                "kind":    "SECTOR_VAR_BUDGET_BREACH",
                "entity":  row["sector"],
                "detail":  f"sector {row['sector']} contributes {row['var_contribution']:.4f}"
                            f" exceeding sector budget {BUDGET_PER_SECTOR_VAR}",
                "severity": "MEDIUM",
            })

    if alerts:
        verdict = "WARNING" if any(a["severity"] == "MEDIUM" for a in alerts) else "PASS"
        verdict = "BLOCK" if any(a["severity"] == "HIGH" for a in alerts) else verdict
    else:
        verdict = "PASS"

    return RiskDecision(
        portfolio_vol_annual=round(port_vol, 4),
        var_95=round(var_95, 4),
        var_99=round(var_99, 4),
        cvar_95=round(cvar_95, 4),
        per_position=per_position,
        per_sector=per_sector,
        budget_utilisation=budget_utilisation,
        alerts=alerts,
        verdict=verdict,
    )


def to_dict(d: RiskDecision) -> dict:
    return {
        "portfolio_vol_annual": d.portfolio_vol_annual,
        "var_95":               d.var_95,
        "var_99":               d.var_99,
        "cvar_95":              d.cvar_95,
        "per_position":         d.per_position,
        "per_sector":           d.per_sector,
        "budget_utilisation":   d.budget_utilisation,
        "alerts":               d.alerts,
        "verdict":              d.verdict,
    }
