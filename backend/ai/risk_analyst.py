"""AI Risk Analyst v1.0 — descriptive audit of the sized-positions batch.

Reads RiskReport + SizedPosition list. Emits:
  - Portfolio composition summary
  - Budget audit: fraction of positions capped by each reason
  - Regime consistency check
  - Downgrade candidates (positions marginally above confidence gate)
  - Breach highlights

**Never emits buy/sell/promoted/approved keys.** Contract-tested.
"""
from __future__ import annotations

from datetime import date
from collections import Counter

from backend.ai.base import AgentOutput
from backend.risk.types import RiskReport, SizedPosition

VERSION = "v1.0"


def run(report: RiskReport, positions: list[SizedPosition],
         market_name: str, asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Composition
    findings.append({
        "type": "portfolio_composition",
        "n_positions":               report.n_positions,
        "n_long":                    report.n_long,
        "n_short":                   report.n_short,
        "gross_exposure_pct":        report.gross_exposure_pct,
        "net_exposure_pct":          report.net_exposure_pct,
        "cash_pct":                  report.cash_pct,
        "hhi":                       report.hhi_concentration,
        "top_5_concentration_pct":   report.top_5_concentration_pct,
        "portfolio_vol_annualised":  report.portfolio_vol_annualised,
        "var_95_1d_pct":             report.portfolio_var_95_1d_pct,
        "cvar_95_1d_pct":            report.portfolio_cvar_95_1d_pct,
    })

    # Cap-reason breakdown (why did positions end up where they did?)
    reasons = Counter(p.cap_reason.value for p in positions)
    findings.append({
        "type":            "cap_reason_breakdown",
        "distribution":    dict(reasons),
        "n_positions":     len(positions),
        "n_dropped_by_confidence_gate":
            reasons.get("confidence_gate", 0),
        "n_dropped_by_disagreement":
            reasons.get("disagreement", 0),
        "n_dropped_short_disabled":
            reasons.get("short_disabled", 0),
    })

    # Regime consistency
    regime_note: str | None = None
    if report.regime == "bull" and report.n_long < report.n_short:
        regime_note = "bull regime but net short — inputs likely inconsistent"
    if report.regime in ("bear", "stress") and report.n_long > report.n_short and report.gross_exposure_pct > 0.6:
        regime_note = f"{report.regime} regime yet gross long exposure > 60% — verify calibration"
    if report.regime == "stress" and report.cash_pct < 0.30:
        regime_note = "stress regime but cash < 30% — consider tightening risk budget"
    if regime_note:
        findings.append({"type": "regime_anomaly", "note": regime_note})

    # Downgrade candidates — positions whose confidence sits just above the gate
    borderline = [p for p in positions
                  if p.cap_reason.value != "confidence_gate"
                  and 0.30 <= p.confidence < 0.40
                  and abs(p.target_weight) > 0]
    for p in borderline[:5]:
        findings.append({
            "type":               "downgrade_candidate",
            "ticker":             p.ticker,
            "action":             p.action,
            "confidence":         p.confidence,
            "target_weight":      p.target_weight,
            "note":               "small drop in confidence would exit this position",
        })

    # Breach highlights
    for b in (report.breaches or [])[:5]:
        findings.append({"type": "breach", **b})

    # Headline
    head = (f"{report.n_positions} positions · gross {report.gross_exposure_pct * 100:.1f}% · "
             f"cash {report.cash_pct * 100:.1f}% · HHI {report.hhi_concentration:.3f} · "
             f"port vol {report.portfolio_vol_annualised * 100:.1f}% · verdict {report.verdict}")
    narr = (head + ".\n\n"
             "This is a descriptive risk audit of the sized-positions batch. "
             "It surfaces composition, cap-reason distribution, regime anomalies, and any breaches. "
             "It does NOT approve or promote positions — every sized position is EXPERIMENTAL until "
             "promoted via backend.promotion.promotion_gate.approve_model with WF evidence.")

    return AgentOutput(
        agent="risk_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={"n_positions": report.n_positions,
                    "gross_exposure_pct": report.gross_exposure_pct,
                    "verdict": report.verdict, "regime": report.regime},
        citations=["backend/risk/engine.py", "configs/risk_budget.yaml"],
        confidence=0.85,
        caveats=[
            "parametric VaR/CVaR uses zero-correlation approximation",
            "sizing is greedy per rec (Sprint 5 Portfolio Engine does joint optimisation)",
            "descriptive only — never promotes",
        ],
        determinism="template",
    )
