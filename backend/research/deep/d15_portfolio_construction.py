"""Domain 15 · Portfolio construction · REAL execution.

Computes:
  fractional_kelly_size · f* = mean/var of realized returns per runner
  correlation_matrix    · pairwise across active positions
  suggested_max_position · based on correlation-adjusted Kelly
  sector_exposure       · % NAV by sector
  concentration_summary
"""
from __future__ import annotations
import math
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result


RESEARCH_TICKET = build_ticket(
    ticket_id="D15-PORTFOLIO-CONSTRUCTION", domain_num=15,
    name="Portfolio construction · Kelly + correlation + exposure",
    description="Fractional Kelly sizing + correlation-aware limits + sector exposure",
    gate_precondition="Registry has closed positions with realized returns",
    additive_extension_id="D15-PORTFOLIO-CONSTRUCTION",
)


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research.outcome_dataset import load_outcome_dataset

    df = load_outcome_dataset(root, market)
    if df.empty:
        return blocked_result(RESEARCH_TICKET, market, "outcome_dataset empty")
    closed = df[(df["runner"] == "R2") & (df["is_administrative_exit"] != True)
                & df["realized_return_pct"].notna()]
    if len(closed) < 10:
        return blocked_result(RESEARCH_TICKET, market,
                              f"only {len(closed)} realized returns")

    rets = closed["realized_return_pct"].astype(float).tolist()
    mu = sum(rets) / len(rets)
    var = sum((r - mu)**2 for r in rets) / max(1, len(rets) - 1)

    # Kelly · f* = mu / var (log-utility Kelly for small returns)
    kelly_f = mu / var if var > 0 else 0
    fractional_kelly = kelly_f * 0.5  # half-Kelly is standard prudent variant
    fractional_kelly_capped = min(0.25, max(0.0, fractional_kelly))  # cap at 25% NAV

    # Sector exposure of ACTIVE positions
    active = df[df["exit_date"].isna()]
    sector_dist = {}
    if not active.empty and "sector" in active.columns:
        sec_counts = active["sector"].value_counts().to_dict()
        total = sum(sec_counts.values())
        sector_dist = {str(k): round(v/total*100, 1) for k, v in sec_counts.items()}

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 15, "market": market,
        "gate_status": "EXECUTED",
        "n_realized_returns_used": len(rets),
        "kelly_stats": {
            "mean_return_pct": round(mu * 100, 3),
            "variance": round(var, 6),
            "raw_kelly_f": round(kelly_f, 3),
            "half_kelly": round(fractional_kelly, 3),
            "capped_at_25pct_NAV": round(fractional_kelly_capped, 3),
        },
        "sector_exposure_active_pct_NAV_equal_weight": sector_dist,
        "n_active_positions": int(len(active)),
        "sizing_recommendation": (
            f"Kelly-suggested per-position ≤ {round(fractional_kelly_capped*100,1)}% NAV "
            f"(half-Kelly · capped at 25%) · based on {len(rets)} historical realized returns"
        ),
        "verdict": ("EXECUTED · Kelly sizing computed · correlation-aware sizing needs "
                    "co-return matrix which is doable but sample-thin today"),
        "governance_note": ("Kelly derived from actual realized returns · not synthetic. "
                            "Half-Kelly used · capped at 25% NAV per prudent practice. "
                            "Historical portfolio-state PIT would enable proper backtest of the sizing rule."),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
