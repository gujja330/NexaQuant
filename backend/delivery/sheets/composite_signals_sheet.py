"""06_Composite_Signals sheet builder · CEO 2026-09-03 pasted-plan §11.

Shadow-only meta-ensemble output. Never contributes to Portfolio P&L.
"""
from __future__ import annotations

from datetime import datetime

COMPOSITE_COLUMNS = [
    "Ticker", "Sector",
    "R1 Score", "R2 Score", "R3 Score",
    "R1 Weight", "R2 Weight", "R3 Weight",
    "Composite Score", "Conviction Class",
    "N Runners Active", "R3 Admitted?",
    "Notes",
]

COMPOSITE_BANNER = (
    "⚠️ RESEARCH ONLY · DO NOT USE FOR INVESTMENT DECISIONS · "
    "COMPOSITE META-ENSEMBLE · shadow only · zero contribution to production P&L. "
    "R3 admitted only when trailing_closed_trades(R3) >= 50 (typically post Day-60). "
    "Promotion of this signal set to primary operator recommendation requires "
    "explicit CEO authorization (named + dated + written)."
)


def build_composite_rows(root, market: str, asof: str,
                         per_ticker_scores: list[dict],
                         trailing_ic: dict,
                         trailing_n: dict) -> list[list]:
    """per_ticker_scores · [{ticker, sector, R1_score, R2_score, R3_score}, ...]
       trailing_ic / trailing_n · per-runner rolling stats
    """
    from backend.recommendation.composite import compute_composite_score
    from pathlib import Path

    rows = []
    for r in per_ticker_scores:
        rs = {
            "R1": float(r.get("R1_score") or 0),
            "R2": float(r.get("R2_score") or 0),
            "R3": float(r.get("R3_score") or 0),
        }
        result = compute_composite_score(rs, trailing_ic, trailing_n,
                                         root=Path(root))
        w = result["trust_weights_normalized"]
        rows.append([
            str(r.get("ticker") or "").upper(),
            r.get("sector") or "",
            round(rs["R1"], 4), round(rs["R2"], 4), round(rs["R3"], 4),
            round(w["R1"], 4), round(w["R2"], 4), round(w["R3"], 4),
            round(result["composite_score"], 4),
            result["conviction"],
            result["n_runners_active"],
            "YES" if result["admissions"]["R3"] == "ADMITTED" else "NO",
            "shadow only · no P&L",
        ])
    return rows


def sheet_meta() -> dict:
    return {
        "sheet_name": "06_Composite_Signals",
        "banner": COMPOSITE_BANNER,
        "columns": COMPOSITE_COLUMNS,
        "notes": [
            "Composite reads admitted runners per configs/aegis_runner_registry.yaml",
            "R3 admission gate: trailing_closed_trades(R3) >= 50",
            "Trust_Weight(r) = 0 for any runner below sample floor",
        ],
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
