"""R3 Tier-3 · CUSUM Change-Point Regime Detection · PDF R3 Tier-3 (V2 §7).

    S_t = max(0, S_{t-1} + (x_t − μ_0 − k))
    Regime shift flagged when S_t > h.

Parameters h and k tuned against historical regime-transition dates.
Must be tested as LEADING indicator vs existing classifier (V2 §7)
before considered as a supplement · never replaces the classifier.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="CUSUM_REGIME_SUPPLEMENT",
    tier=3,
    name="CUSUM regime change-point supplement",
    description="Positive one-sided CUSUM · flags shift when S_t > h · tested as leading indicator to existing classifier",
    gate_precondition="Regime enricher live (LANDED) + historical regime-transition dates labelled + leading-indicator test methodology defined",
    pdf_reference="V2 §7 · CUSUM as supplemental Tier-3 research · never replaces regime classifier",
    additive_extension_id="CUSUM_REGIME_SUPPLEMENT",
)

# Default parameters (tuned separately per market · these are illustrative)
CUSUM_K_DEFAULT = 0.5     # slack
CUSUM_H_DEFAULT = 5.0     # threshold


def cusum_stream(returns: list[float], mu_0: float = 0.0,
                 k: float = CUSUM_K_DEFAULT,
                 h: float = CUSUM_H_DEFAULT) -> list[dict]:
    """One-sided positive CUSUM stream · returns list of {t, S, flagged}."""
    S = 0.0
    out: list[dict] = []
    for t, x in enumerate(returns):
        try:
            xv = float(x)
        except (TypeError, ValueError):
            continue
        S = max(0.0, S + (xv - mu_0 - k))
        out.append({"t": t, "S": round(S, 4), "flagged": S > h})
    return out


def leading_indicator_test(cusum_flag_dates: list[str],
                           classifier_transition_dates: list[str],
                           lead_window_days: int = 5) -> dict:
    """For each classifier transition · was CUSUM flagged in the preceding
    `lead_window_days`? Returns lead-hit rate + false-flag rate."""
    from datetime import date, timedelta
    if not classifier_transition_dates:
        return {"lead_hit_rate": 0.0, "false_flag_rate": 0.0, "n_transitions": 0}
    n_hit = 0
    for td in classifier_transition_dates:
        try:
            td_d = date.fromisoformat(td)
        except Exception:
            continue
        window_start = td_d - timedelta(days=lead_window_days)
        if any(window_start <= date.fromisoformat(f) <= td_d
               for f in cusum_flag_dates if _iso_ok(f)):
            n_hit += 1
    false_flags = sum(1 for f in cusum_flag_dates
                      if _iso_ok(f) and f not in classifier_transition_dates)
    return {
        "n_transitions": len(classifier_transition_dates),
        "lead_hit_rate": n_hit / len(classifier_transition_dates),
        "false_flag_rate": false_flags / max(1, len(cusum_flag_dates)),
    }


def _iso_ok(s: str) -> bool:
    from datetime import date
    try: date.fromisoformat(s); return True
    except Exception: return False


def evaluate(root: Path, market: str) -> dict:
    reg_path = root / "reports" / "research" / f"mr_market_regime_{market}.json"
    if not reg_path.exists():
        return blocked_result(RESEARCH_TICKET, market,
                              f"regime source missing at {reg_path.name}",
                              extra_artifacts=[
                                  f"reports/research/r3/tier3/cusum_regime_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Extract historical daily returns · run cusum_stream · label transition dates from mr_market_regime · leading_indicator_test with lead=5d",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
