"""DEV027 diagnostic rules — 15 failure categories operator specified.

Every diagnostic is a pure function that inspects a single closed trade
and returns (fires: bool, evidence: str, severity: str). Non-firing
diagnostics return (False, "", "NONE").
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Diagnosis:
    category: str
    fires: bool
    evidence: str
    severity: str                       # LOW / MEDIUM / HIGH / CRITICAL


# ── 15 failure categories from DEV027 spec ─────────────────────────────────

def wrong_company(trade: dict) -> Diagnosis:
    """Company-level: score was inflated by a single dimension without breadth."""
    if trade.get("return_pct", 0) >= 0:
        return Diagnosis("wrong_company", False, "", "NONE")
    high_score_low_confidence = (trade.get("score_at_entry", 0) >= 70 and
                                    trade.get("confidence", 1) < 0.6)
    if high_score_low_confidence:
        return Diagnosis("wrong_company", True,
                          f"score {trade['score_at_entry']:.1f} but confidence "
                          f"{trade['confidence']:.2f} — score-confidence mismatch",
                          "MEDIUM")
    return Diagnosis("wrong_company", False, "", "NONE")


def wrong_sector(trade: dict, sector_context: dict) -> Diagnosis:
    """Loss while parent sector was already weak."""
    if trade.get("return_pct", 0) >= 0:
        return Diagnosis("wrong_sector", False, "", "NONE")
    sec = trade.get("sector")
    if sec is None:
        return Diagnosis("wrong_sector", False, "", "NONE")
    # Look up sector score in the DEV018 context
    for s in (sector_context or {}).get("sectors", []):
        if s.get("display_name") == sec and s.get("status") == "computed":
            if s.get("score", 100) < 45:
                return Diagnosis("wrong_sector", True,
                                  f"sector {sec} was Weak/Neutral at "
                                  f"score {s['score']:.1f}",
                                  "HIGH")
            break
    return Diagnosis("wrong_sector", False, "", "NONE")


def wrong_regime(trade: dict, global_context: dict) -> Diagnosis:
    if trade.get("return_pct", 0) >= 0:
        return Diagnosis("wrong_regime", False, "", "NONE")
    if not global_context:
        return Diagnosis("wrong_regime", False, "", "NONE")
    posture = (global_context.get("classifications", {}) or {}).get("global_posture", {}).get("label")
    if posture == "Risk-Off":
        return Diagnosis("wrong_regime", True,
                          f"trade entered under global Risk-Off regime",
                          "MEDIUM")
    return Diagnosis("wrong_regime", False, "", "NONE")


def late_entry(trade: dict) -> Diagnosis:
    """MFE occurred very early (within 20% of hold) then reverted."""
    if trade.get("return_pct", 0) >= 0:
        return Diagnosis("late_entry", False, "", "NONE")
    mfe = trade.get("mfe_pct", 0)
    if mfe > 5 and trade.get("return_pct", 0) < -3:
        return Diagnosis("late_entry", True,
                          f"peaked at +{mfe:.1f}% then closed at "
                          f"{trade['return_pct']:.1f}% — bought after peak",
                          "MEDIUM")
    return Diagnosis("late_entry", False, "", "NONE")


def early_exit(trade: dict) -> Diagnosis:
    """MFE was materially larger than realised return — exited too early."""
    if trade.get("return_pct", 0) <= 0:
        return Diagnosis("early_exit", False, "", "NONE")
    mfe = trade.get("mfe_pct", 0)
    ret = trade.get("return_pct", 0)
    if mfe > ret + 5 and ret > 0:
        return Diagnosis("early_exit", True,
                          f"peaked at +{mfe:.1f}% but exited at only +{ret:.1f}%",
                          "LOW")
    return Diagnosis("early_exit", False, "", "NONE")


def weak_conviction(trade: dict) -> Diagnosis:
    if trade.get("confidence", 1) < 0.6 and trade.get("return_pct", 0) < 0:
        return Diagnosis("weak_conviction", True,
                          f"confidence {trade['confidence']:.2f} < 0.6, lost "
                          f"{trade['return_pct']:.1f}%",
                          "MEDIUM")
    return Diagnosis("weak_conviction", False, "", "NONE")


def overconfidence(trade: dict) -> Diagnosis:
    if trade.get("confidence", 0) >= 0.85 and trade.get("return_pct", 0) < -5:
        return Diagnosis("overconfidence", True,
                          f"confidence {trade['confidence']:.2f} but loss "
                          f"{trade['return_pct']:.1f}% — miscalibrated",
                          "HIGH")
    return Diagnosis("overconfidence", False, "", "NONE")


def underconfidence(trade: dict) -> Diagnosis:
    if trade.get("confidence", 0) < 0.6 and trade.get("return_pct", 0) > 8:
        return Diagnosis("underconfidence", True,
                          f"confidence only {trade['confidence']:.2f} but gained "
                          f"{trade['return_pct']:.1f}% — underweighted a winner",
                          "LOW")
    return Diagnosis("underconfidence", False, "", "NONE")


def high_correlation(trade: dict, cohort_trades: list[dict]) -> Diagnosis:
    """Same-sector concentration risk visible in a losing cohort."""
    if trade.get("return_pct", 0) >= 0:
        return Diagnosis("high_correlation", False, "", "NONE")
    sec = trade.get("sector")
    cohort_sec = [t for t in cohort_trades if t.get("sector") == sec]
    losing_cohort = [t for t in cohort_sec if t.get("return_pct", 0) < 0]
    if len(cohort_sec) >= 3 and len(losing_cohort) / len(cohort_sec) > 0.7:
        return Diagnosis("high_correlation", True,
                          f"{len(losing_cohort)}/{len(cohort_sec)} same-sector trades "
                          f"in cohort {trade.get('entry_date')} were losers",
                          "MEDIUM")
    return Diagnosis("high_correlation", False, "", "NONE")


def excess_concentration(trade: dict, cohort_trades: list[dict]) -> Diagnosis:
    """Cohort had >30% weight in one sector."""
    sec = trade.get("sector")
    if not sec:
        return Diagnosis("excess_concentration", False, "", "NONE")
    same_sec = [t for t in cohort_trades if t.get("sector") == sec]
    if len(same_sec) >= 5 and len(same_sec) / max(1, len(cohort_trades)) > 0.30:
        return Diagnosis("excess_concentration", True,
                          f"{sec} accounted for {len(same_sec)}/{len(cohort_trades)} "
                          f"trades in cohort — over-concentrated",
                          "MEDIUM" if trade.get("return_pct", 0) < 0 else "LOW")
    return Diagnosis("excess_concentration", False, "", "NONE")


def stop_loss_ineffective(trade: dict) -> Diagnosis:
    """Trade went -5% but ultimately closed profitable — stop would have hurt."""
    mae = trade.get("mae_pct", 0)
    ret = trade.get("return_pct", 0)
    if mae < -5 and ret > 3:
        return Diagnosis("stop_loss_ineffective", True,
                          f"dipped to {mae:.1f}% but recovered to {ret:.1f}% — "
                          "a -5% stop would have exited too early",
                          "LOW")
    return Diagnosis("stop_loss_ineffective", False, "", "NONE")


def liquidity_shock(trade: dict) -> Diagnosis:
    """Extreme adverse move consistent with liquidity gap (would need volume history)."""
    mae = trade.get("mae_pct", 0)
    if mae < -15 and trade.get("return_pct", 0) < -8:
        return Diagnosis("liquidity_shock", True,
                          f"MAE of {mae:.1f}% suggests thin liquidity or news gap",
                          "HIGH")
    return Diagnosis("liquidity_shock", False, "", "NONE")


def macro_shock(trade: dict, cohort_trades: list[dict]) -> Diagnosis:
    """When >60% of cohort loses, it's a market-wide event not a pick."""
    losing = [t for t in cohort_trades if t.get("return_pct", 0) < 0]
    if len(cohort_trades) >= 10 and len(losing) / len(cohort_trades) > 0.6:
        return Diagnosis("macro_shock", True,
                          f"{len(losing)}/{len(cohort_trades)} cohort trades losing "
                          f"— market-wide event, not stock-selection",
                          "HIGH" if trade.get("return_pct", 0) < 0 else "INFO")
    return Diagnosis("macro_shock", False, "", "NONE")


def volatility_risk(trade: dict) -> Diagnosis:
    """Wild swing — MFE and MAE both large."""
    mfe = trade.get("mfe_pct", 0)
    mae = trade.get("mae_pct", 0)
    if mfe > 10 and mae < -10:
        return Diagnosis("volatility_risk", True,
                          f"trade oscillated between {mae:.1f}% and +{mfe:.1f}%",
                          "MEDIUM")
    return Diagnosis("volatility_risk", False, "", "NONE")


def poor_diversification(cohort_trades: list[dict]) -> Diagnosis:
    """Cohort has too few sectors represented."""
    sectors = {t.get("sector") for t in cohort_trades if t.get("sector")}
    if len(cohort_trades) >= 10 and len(sectors) <= 3:
        return Diagnosis("poor_diversification", True,
                          f"only {len(sectors)} sector(s) in {len(cohort_trades)}-trade cohort",
                          "MEDIUM")
    return Diagnosis("poor_diversification", False, "", "NONE")


# ── Registry ─────────────────────────────────────────────────────────────────

ALL_DIAGNOSTICS = [
    "wrong_company", "wrong_sector", "wrong_regime",
    "late_entry", "early_exit",
    "weak_conviction", "overconfidence", "underconfidence",
    "high_correlation", "excess_concentration",
    "stop_loss_ineffective", "liquidity_shock", "macro_shock",
    "volatility_risk", "poor_diversification",
]
