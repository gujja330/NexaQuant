"""Domain 20 · Failure Research Extension (WAVE 1 · real).

Extends NEG-PNL/POS-PNL/zero-entry with a 4-category failure decomposition
for every realized loss:
  model_failure    · signal was wrong · high confidence but wrong direction
  data_failure     · stale/missing data at entry decision
  regime_failure   · regime shifted between entry and exit
  portfolio_failure · position was correct but portfolio-level rule failed

Only executes against Outcome Dataset with realized_return_pct present.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.research.deep._helpers import (
    build_ticket, blocked_result, insufficient_sample, emit_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="D20-FAILURE-RESEARCH-EXT",
    domain_num=20,
    name="Failure Research Extension · 4-category loss decomposition",
    description="model_failure / data_failure / regime_failure / portfolio_failure per loss",
    gate_precondition="Outcome Dataset ≥ 30 realized losses",
    additive_extension_id="D20-FAILURE-EXT",
)


def _classify_failure(row) -> str:
    """Heuristic 4-category classifier · uses fields available today."""
    # Model failure: entry_signal_score was high but realized was negative
    score = row.get("entry_signal_score")
    realized = row.get("realized_return_pct", 0)
    conf = row.get("entry_calibrated_conf")
    regime_entry = row.get("regime_at_entry")

    if score is not None and conf is not None:
        try:
            if float(score) > 0.5 and float(conf) > 0.6 and float(realized) < -0.05:
                return "MODEL_FAILURE · high-confidence wrong-direction"
        except (TypeError, ValueError): pass

    # Data failure: missing entry_price or entry_signal_score
    if score is None or row.get("entry_price") is None:
        return "DATA_FAILURE · missing decision-time features"

    # Regime failure: entry regime differs from what we'd expect for exit
    # (proxy · needs regime_at_exit which isn't in schema · flag when regime=UNKNOWN)
    if regime_entry in (None, "UNKNOWN"):
        return "REGIME_FAILURE · unknown regime at entry (context missing)"

    # Portfolio failure: default for anything else · position level looked ok
    return "PORTFOLIO_OR_UNKNOWN_FAILURE · needs portfolio-state PIT"


def evaluate(root: Path, market: str) -> dict:
    from collections import Counter
    from backend.research.outcome_dataset import load_outcome_dataset

    df = load_outcome_dataset(root, market)
    if df.empty:
        return blocked_result(RESEARCH_TICKET, market, "outcome_dataset empty")
    df = df[(df["runner"] == "R2") & (df["is_administrative_exit"] != True)
             & (df["realized_return_pct"] < 0) & df["realized_return_pct"].notna()]
    if len(df) < 30:
        return insufficient_sample(RESEARCH_TICKET, market, int(len(df)), 30)

    cats = Counter()
    for _, r in df.iterrows():
        cats[_classify_failure(r.to_dict())] += 1

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 20,
        "market": market,
        "gate_status": "EXECUTED",
        "n_losses_classified": int(len(df)),
        "failure_category_distribution": dict(cats),
        "governance_note": ("Heuristic classification using available Outcome Dataset "
                            "fields · true classification needs richer per-position "
                            "context (entry_signal_score history · regime at exit · "
                            "portfolio state at entry) · gaps flagged as REGIME_FAILURE / "
                            "PORTFOLIO_OR_UNKNOWN_FAILURE."),
        "verdict": "RESEARCH FURTHER · substrate expansion required for cleaner attribution",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
