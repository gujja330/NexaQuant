"""DNA Outcome Backfill · resolves B-2 blocker (0/84 populated).

Cross-references `data/aegis_recommendation_db.csv` (84 DNA records with
recommended_date + symbol + entry + target) against `reports/learning.parquet`
(1060 closed trades with entry_date + exit_date + ticker + return_pct + MFE
+ MAE + n_bars_held) to populate the outcome fields for the DNA registry.

Match logic: same ticker AND entry_date within 5 trading days of DNA
recommended_date.

Article 101.2 · data-backfill permitted. No new engine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_FINGERPRINT = "aegis.certification.dna_outcome_backfill.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.certification.dna_outcome_backfill.v1"

MATCH_WINDOW_DAYS = 5


@dataclass
class BackfillReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    n_dna_records: int = 0
    n_learning_trades: int = 0
    n_matched: int = 0
    n_unmatched_dna: int = 0
    match_rate_pct: float = 0.0
    per_symbol_matches: dict = field(default_factory=dict)
    backfilled_records: list = field(default_factory=list)


def run_backfill(root: Path) -> BackfillReport:
    import pandas as pd
    rep = BackfillReport(run_utc=datetime.now(timezone.utc).isoformat())
    dna_p = root / "data" / "aegis_recommendation_db.csv"
    learn_p = root / "reports" / "learning.parquet"
    if not dna_p.exists() or not learn_p.exists():
        return rep

    dna = pd.read_csv(dna_p)
    learning = pd.read_parquet(learn_p)
    rep.n_dna_records = len(dna)
    rep.n_learning_trades = len(learning)

    # Normalize dates
    if "recommended_date" in dna.columns:
        dna["recommended_date"] = pd.to_datetime(dna["recommended_date"], errors="coerce")
    if "entry_date" in learning.columns:
        learning["entry_date"] = pd.to_datetime(learning["entry_date"], errors="coerce")

    # Phase C fix (2026-07-27): normalize ticker suffix on BOTH sides.
    # DNA registry has bare symbols (RELIANCE) · learning.parquet has NSE-suffixed
    # symbols (RELIANCE.NS). Strip suffix on both sides for comparison.
    def _bare(t) -> str:
        s = str(t).upper().strip()
        return s.split(".")[0] if "." in s else s
    learning["_ticker_bare"] = learning["ticker"].map(_bare)

    for _, drec in dna.iterrows():
        sym = _bare(drec.get("symbol", ""))
        rec_date = drec.get("recommended_date")
        if not sym or pd.isna(rec_date):
            rep.n_unmatched_dna += 1
            continue
        candidates = learning[
            (learning["_ticker_bare"] == sym) &
            (learning["entry_date"].between(
                rec_date - pd.Timedelta(days=MATCH_WINDOW_DAYS),
                rec_date + pd.Timedelta(days=MATCH_WINDOW_DAYS)
            ))
        ]
        if len(candidates) == 0:
            rep.n_unmatched_dna += 1
            continue
        # Pick nearest entry_date
        candidates = candidates.copy()
        candidates["_delta"] = (candidates["entry_date"] - rec_date).abs()
        best = candidates.sort_values("_delta").iloc[0]

        outcome = {
            "symbol": sym,
            "dna_recommended_date": str(rec_date.date()) if rec_date else None,
            "matched_entry_date": str(best["entry_date"].date()) if pd.notna(best["entry_date"]) else None,
            "matched_exit_date": str(best.get("exit_date")) if pd.notna(best.get("exit_date")) else None,
            "outcome_return_pct": round(float(best.get("return_pct", 0.0)), 4) if pd.notna(best.get("return_pct")) else None,
            "outcome_mfe_pct": round(float(best.get("mfe_pct", 0.0)), 4) if pd.notna(best.get("mfe_pct")) else None,
            "outcome_mae_pct": round(float(best.get("mae_pct", 0.0)), 4) if pd.notna(best.get("mae_pct")) else None,
            "outcome_n_bars_held": int(best.get("n_bars_held", 0)) if pd.notna(best.get("n_bars_held")) else None,
            "outcome_is_winner": bool(best.get("is_winner", False)) if pd.notna(best.get("is_winner")) else None,
            "outcome_hit_5pct_target": bool(best.get("hit_5pct_target", False)) if pd.notna(best.get("hit_5pct_target")) else None,
            "outcome_hit_5pct_stop": bool(best.get("hit_5pct_stop", False)) if pd.notna(best.get("hit_5pct_stop")) else None,
            "match_delta_days": int(best["_delta"].days) if pd.notna(best["_delta"]) else None,
        }
        rep.backfilled_records.append(outcome)
        rep.per_symbol_matches[sym] = rep.per_symbol_matches.get(sym, 0) + 1

    rep.n_matched = len(rep.backfilled_records)
    if rep.n_dna_records > 0:
        rep.match_rate_pct = round(rep.n_matched / rep.n_dna_records * 100, 2)
    return rep
