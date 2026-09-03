"""Domain 16 · Deep Exit Science (WAVE 1 · real).

Beyond existing P0/NEG-PNL/POS-PNL:
  signal_deterioration_exit · exit when calibrated_confidence drops N pp
  regime_exit_check · exit when regime transitions to CRASH/RISK_OFF
  MAE_MFE_frontier · plot per-position winner-preservation vs loss-containment
  time_to_recover_ratio · median days to recover from worst_pct across positions
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.research.deep._helpers import (
    build_ticket, blocked_result, emit_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="D16-DEEP-EXIT-SCIENCE",
    domain_num=16,
    name="Deep exit science · signal-deterioration + regime + MAE/MFE",
    description="Extensions beyond P0 exit-bridge · uses Outcome Dataset + regime enricher",
    gate_precondition="Outcome Dataset ≥ 30 non-admin closed R2 positions",
    additive_extension_id="D16-DEEP-EXIT-SCIENCE",
)


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research.outcome_dataset import load_outcome_dataset
    df = load_outcome_dataset(root, market)
    if df.empty:
        return blocked_result(RESEARCH_TICKET, market, "outcome_dataset empty")
    df = df[(df["runner"] == "R2") & (df["is_administrative_exit"] != True)
             & df["realized_return_pct"].notna()]
    if len(df) < 30:
        from backend.research.deep._helpers import insufficient_sample
        return insufficient_sample(RESEARCH_TICKET, market, int(len(df)), 30)

    # MAE / MFE decomposition
    mae_vals = df["max_adverse_excursion"].dropna().tolist() if "max_adverse_excursion" in df.columns else []
    mfe_vals = df["max_favorable_excursion"].dropna().tolist() if "max_favorable_excursion" in df.columns else []
    realized = df["realized_return_pct"].tolist()

    # Buckets
    winners = [r for r in realized if r > 0]
    losers = [r for r in realized if r < 0]
    deep_losers = [r for r in realized if r <= -0.10]

    # Regime-conditional exit test · if regime_at_entry populated
    per_regime = {}
    if "regime_at_entry" in df.columns:
        for reg, sub in df.groupby("regime_at_entry"):
            per_regime[str(reg)] = {
                "n": int(len(sub)),
                "mean_realized": float(sub["realized_return_pct"].mean()),
                "loss_rate": float((sub["realized_return_pct"] < 0).sum() / len(sub)),
            }

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 16,
        "market": market,
        "gate_status": "EXECUTED",
        "n_positions": int(len(df)),
        "mae_mfe_summary": {
            "mean_mae": (sum(mae_vals) / len(mae_vals)) if mae_vals else None,
            "mean_mfe": (sum(mfe_vals) / len(mfe_vals)) if mfe_vals else None,
            "n_deep_losers": len(deep_losers),
            "n_winners": len(winners),
            "n_losers": len(losers),
        },
        "regime_conditioned": per_regime,
        "signal_deterioration_exit_test": {
            "note": "Requires per-position confidence timeseries · Signal Ledger too thin today",
            "blocker": "SIGNAL_LEDGER_HISTORY_INSUFFICIENT",
        },
        "governance_note": ("MAE/MFE + regime split available today · signal-deterioration "
                            "exit test blocked until Signal Ledger accumulates per-position timeseries."),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
