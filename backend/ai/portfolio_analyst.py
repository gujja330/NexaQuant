"""AI Portfolio Analyst v1.0 — descriptive audit of the constructed portfolio.

Reads PortfolioSnapshot + PortfolioDiff. Emits:
  - Composition summary
  - Diversification quality (HHI · effective_N · top-5 · sector spread)
  - Turnover assessment (are we churning?)
  - Concentration risks
  - Cash policy compliance
  - Rebalance efficiency

Never emits buy/sell/promoted/approved keys (contract-tested).
"""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput
from backend.portfolio.types import PortfolioSnapshot, PortfolioDiff

VERSION = "v1.0"


def run(snap: PortfolioSnapshot, diff: PortfolioDiff,
         effective_n_min: float, turnover_warning_threshold: float,
         market_name: str, asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Composition
    findings.append({
        "type":            "composition",
        "n_positions":     snap.n_positions,
        "n_long":          sum(1 for p in snap.positions if p.weight > 0),
        "n_short":         sum(1 for p in snap.positions if p.weight < 0),
        "total_weight":    snap.total_weight,
        "cash_pct":        snap.cash_pct,
        "cash_reserve_target": snap.cash_reserve_target,
    })

    # Diversification quality
    findings.append({
        "type":         "diversification",
        "hhi":          snap.hhi,
        "effective_n":  snap.effective_n,
        "top_5_pct":    snap.top_5_pct,
        "n_sectors":    snap.n_sectors,
        "per_sector_pct": snap.per_sector_pct,
    })
    if snap.effective_n > 0 and snap.effective_n < effective_n_min:
        findings.append({
            "type": "concentration_warning",
            "effective_n": snap.effective_n,
            "threshold":   effective_n_min,
            "note": f"effective N ({snap.effective_n:.1f}) below policy floor ({effective_n_min}) — portfolio too concentrated",
        })

    # Sector concentration
    for sec, expo in (snap.per_sector_pct or {}).items():
        if abs(expo) > 0.30:
            findings.append({
                "type": "sector_concentration",
                "sector": sec, "exposure_pct": expo,
                "note": f"sector {sec} exposure {expo * 100:.1f}% > 30% — verify against risk_budget.yaml sector cap",
            })

    # Turnover assessment
    findings.append({
        "type":                       "rebalance_summary",
        "turnover_pct":               diff.turnover_pct,
        "turnover_warning_threshold": turnover_warning_threshold,
        "prior_asof":                 diff.prior_asof.isoformat() if diff.prior_asof else None,
        "n_open":                     diff.n_open,
        "n_close":                    diff.n_close,
        "n_increase":                 diff.n_increase,
        "n_decrease":                 diff.n_decrease,
        "n_hold":                     diff.n_hold,
    })
    if diff.turnover_pct > turnover_warning_threshold:
        findings.append({
            "type": "high_turnover_warning",
            "turnover_pct": diff.turnover_pct,
            "threshold":    turnover_warning_threshold,
            "note": "high daily turnover — consider raising rebalance_threshold_bps or reducing sizing sensitivity",
        })

    # Cash policy compliance
    if snap.cash_pct + 1e-6 < snap.cash_reserve_target:
        findings.append({
            "type": "cash_policy_breach",
            "cash_pct":            snap.cash_pct,
            "cash_reserve_target": snap.cash_reserve_target,
            "note": "actual cash below target — check construction/normalization",
        })

    head = (f"{snap.n_positions} positions · gross {(1.0 - snap.cash_pct) * 100:.1f}% · "
             f"cash {snap.cash_pct * 100:.1f}% · HHI {snap.hhi:.3f} · "
             f"effN {snap.effective_n:.1f} · turnover {diff.turnover_pct * 100:.1f}% · "
             f"regime={snap.regime_at_construction}")
    narr = (head + ".\n\n"
             "Descriptive portfolio audit. Highlights diversification quality, concentration risks, "
             "cash policy compliance, and rebalance turnover. Does NOT approve or promote — every "
             "portfolio snapshot is EXPERIMENTAL until promoted via backend.promotion.promotion_gate."
             " Trades in portfolio_diff.json are candidate instructions for Sprint 7 Execution Simulator.")

    return AgentOutput(
        agent="portfolio_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={
            "n_positions": snap.n_positions, "cash_pct": snap.cash_pct,
            "hhi": snap.hhi, "effective_n": snap.effective_n,
            "turnover_pct": diff.turnover_pct,
        },
        citations=["backend/portfolio/engine.py", "configs/portfolio_config.yaml"],
        confidence=0.85,
        caveats=[
            "diversification metrics use gross weights",
            "cross-sector optimization is deferred (Sprint 5 uses greedy per-rec construction)",
            "descriptive only — never promotes",
        ],
        determinism="template",
    )
