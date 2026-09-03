"""T4 · Missed-Winner Funnel · classify WHY each winner was missed.

Classification categories A..L per CEO 2026-09-03 master prompt.
Only A..F are cleanly classifiable today from available substrate.
G..L require additional wiring (risk state, portfolio state, R1/R3
scores, composite scores, timing history).

A missed winner is defined as:
    is_winner_at_(horizon, threshold) == True
    AND was_selected_by_aegis == False

For each such candidate, the FIRST applicable category from the walk
downwards is the classification. Order matters:
    A (universe) → B (data) → C (funnel-stage) → D (score) → E (rank)
    → F (confidence gate) → G (risk) → H (capacity) → I (disagreement)
    → J (composite) → K (timing) → L (correct rejection)
"""
from __future__ import annotations

import json
from pathlib import Path

MISS_CATEGORIES = [
    ("A_UNIVERSE_MISS",     "Ticker was NOT in PIT universe on this date"),
    ("B_DATA_MISS",         "Ticker in universe but required PIT data missing"),
    ("C_FUNNEL_STAGE_MISS", "Entered funnel but eliminated by short_term_momentum IGNORE / other pre-score filter"),
    ("D_SCORE_MISS",        "Scored but ensemble_score below action threshold"),
    ("E_RANKING_MISS",      "Scored well but didn't make top-N ranking"),
    ("F_CONFIDENCE_MISS",   "Score+rank good but calibrated_confidence below floor (0.55)"),
    ("G_RISK_MISS",         "Passed confidence but risk controls rejected · NEEDS SUBSTRATE"),
    ("H_PORTFOLIO_MISS",    "Passed risk but portfolio capacity/exposure blocked · NEEDS SUBSTRATE"),
    ("I_RUNNER_DISAGREEMENT","R1/R2/R3 disagreed · NEEDS COMPOSITE"),
    ("J_COMPOSITE_MISS",    "Individual runner saw it, composite didn't · NEEDS COMPOSITE"),
    ("K_TIMING_MISS",       "Detected but late · NEEDS DAILY_RANK_HISTORY"),
    ("L_CORRECT_REJECTION", "Went up subsequently but admission would have violated legitimate risk rule"),
]


def _score_lookup(root: Path, market: str, date_str: str, ticker: str) -> dict | None:
    """Return {ensemble_score, calibrated_confidence, rank} for (date, ticker)
    from recommendations_history if present. Returns None when snapshot missing."""
    import json as _json
    for base in (root / "reports" / "recommendations_history" / market,
                 root / "usa" / "reports" / "recommendations_history" / market):
        p = base / f"{date_str}.json"
        if p.exists():
            try:
                d = _json.loads(p.read_text(encoding="utf-8"))
                for r in (d.get("recommendations") or []):
                    t = str(r.get("ticker","")).upper()
                    t_short = t.split(".",1)[0]
                    if t == ticker or t_short == ticker:
                        return {
                            "ensemble_score": r.get("ensemble_score"),
                            "calibrated_confidence": r.get("calibrated_confidence"),
                            "rank": r.get("rank"),
                        }
            except Exception:
                pass
    return None


def _in_momentum_ledger(root: Path, market: str, date_str: str, ticker: str) -> tuple[bool, str | None]:
    """Was the ticker considered by the momentum ledger on this date?
    Returns (was_considered, terminal_state)."""
    import json as _json
    p = root / "reports" / "research" / "multi_layer" / f"momentum_ledger_{market}_{date_str}.json"
    if not p.exists(): return (False, None)
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
        for e in (d.get("entries") or []):
            t = str(e.get("ticker","")).upper()
            t_short = t.split(".",1)[0]
            if t == ticker or t_short == ticker:
                return (True, e.get("terminal_state"))
        return (False, None)
    except Exception:
        return (False, None)


def classify_missed_winner(root: Path, market: str, date_str: str,
                           ticker: str, was_in_universe: bool,
                           data_available: bool,
                           confidence_floor: float = 0.55,
                           rank_topn: int = 15) -> dict:
    """Assign the FIRST applicable category."""
    if not was_in_universe:
        return {"category": "A_UNIVERSE_MISS",
                "detail": "not in PIT universe on this date"}
    if not data_available:
        return {"category": "B_DATA_MISS",
                "detail": "PIT price parquet missing"}

    considered, terminal_state = _in_momentum_ledger(root, market, date_str, ticker)
    if considered and terminal_state in ("NO_EVIDENCE", "REJECTED"):
        return {"category": "C_FUNNEL_STAGE_MISS",
                "detail": f"momentum_ledger terminal_state={terminal_state}"}
    if not considered:
        # Not in momentum ledger AND in universe AND has data → dropped by IGNORE
        return {"category": "C_FUNNEL_STAGE_MISS",
                "detail": "not in momentum ledger · dropped by short_term_momentum IGNORE filter"}

    scores = _score_lookup(root, market, date_str, ticker)
    if scores is None:
        # Was considered but no scored snapshot exists → substrate gap
        return {"category": "D_SCORE_MISS",
                "detail": "no recommendations_v3 snapshot has this ticker on this date"}

    ens = scores.get("ensemble_score")
    conf = scores.get("calibrated_confidence")
    rank = scores.get("rank")
    if ens is None or ens < 0.3:
        return {"category": "D_SCORE_MISS",
                "detail": f"ensemble_score={ens} below action threshold"}
    if rank is not None and rank > rank_topn:
        return {"category": "E_RANKING_MISS",
                "detail": f"rank={rank} outside top-{rank_topn}"}
    if conf is not None and conf < confidence_floor:
        return {"category": "F_CONFIDENCE_MISS",
                "detail": f"calibrated_confidence={conf} below floor {confidence_floor}"}

    # Anything else is not classifiable today without further substrate
    return {"category": "G_RISK_MISS_OR_LATER_UNKNOWN",
            "detail": "passed confidence gate but not selected · substrate needed for G-L classification"}
