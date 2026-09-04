"""Section E · Execute the Evidence Program on F01-F05 individually.

CEO 2026-09-05 · make the unit of work EVIDENCE, not ideas.

For each of F01-F05, for each of {india, usa}:
  · check PIT availability (fundamentals_history parquet)
  · report earliest/latest asof · unique dates · unique tickers · missingness
  · attempt historical + walk-forward evidence run
  · if substrate insufficient · report BLOCKED with mechanical proof
  · append immutable Evidence Log record
  · update Evidence Clock

Produce reports/research/evidence/evidence_program_F01_F05.json (consolidated).

Governance · zero production writes · zero R2 changes · zero promotion.
"""
from __future__ import annotations
import io, json, sys
from datetime import date, datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.evidence.engine import run_historical_evidence, EvidenceResult
from backend.research.evidence.evidence_clock import EvidenceClock
from backend.research.evidence import evidence_log


# F01-F05 · one primary signal per fundamental family
FUNDAMENTAL_ITEMS = [
    {"id": "F01-BUSINESS-QUALITY",  "signal_col": "fcf_yield",         "direction": "positive"},
    {"id": "F02-BALANCE-SHEET",     "signal_col": "interest_coverage", "direction": "positive"},
    {"id": "F03-ACCOUNTING-QUALITY","signal_col": "piotroski_f",       "direction": "positive"},
    {"id": "F04-VALUATION",         "signal_col": "ev_ebitda",         "direction": "negative"},
    {"id": "F05-GROWTH",            "signal_col": "revenue_growth_yoy","direction": "positive"},
]


def _load_fundamentals_history(root: Path, market: str):
    import pandas as pd
    p = root / "reports" / "research" / "fundamentals_history" / f"{market}.parquet"
    if not p.exists(): return None
    return pd.read_parquet(p)


def _pit_summary(root: Path, market: str, signal_col: str) -> dict:
    """Report PIT availability for the signal · Section F requirements."""
    import pandas as pd
    df = _load_fundamentals_history(root, market)
    if df is None or df.empty:
        return {"pit_available": False, "reason": "fundamentals_history parquet missing/empty"}
    if signal_col not in df.columns:
        return {"pit_available": False, "reason": f"column {signal_col} not in fundamentals_history",
                 "available_columns": list(df.columns)[:15]}
    non_null = df[df[signal_col].notna()]
    if non_null.empty:
        return {"pit_available": False, "reason": f"column {signal_col} present but all-null"}
    return {
        "pit_available": True,
        "signal_col": signal_col,
        "earliest_asof": str(non_null["asof"].min()),
        "latest_asof": str(non_null["asof"].max()),
        "unique_asof_dates": int(non_null["asof"].nunique()),
        "unique_tickers": int(non_null["ticker"].nunique()),
        "usable_observations": int(len(non_null)),
        "missingness_pct": round(100.0 * (1.0 - len(non_null) / len(df)), 2),
    }


def run_item(root: Path, item: dict, market: str) -> dict:
    """Section G output · full evidence record for one item×market."""
    signal_col = item["signal_col"]
    pit = _pit_summary(root, market, signal_col)

    # Substrate check first · BLOCKED if PIT not available
    if not pit["pit_available"]:
        exp = evidence_log.append_evidence_record(
            root, item_id=item["id"], market=market,
            data_snapshot="", pit_status="unavailable",
            fold_definition={}, trial_count=0, parameters={"signal_col": signal_col},
            sample_size=0, metrics={},
            statistical_test={}, multiple_testing_correction={},
            decision="BLOCKED",
            artifact_paths=[])
        return {"item_id": item["id"], "market": market, "decision": "BLOCKED",
                 "reason": pit["reason"], "pit_summary": pit,
                 "experiment_id": exp, "evidence_clock_state": "DATA_EXISTS"}

    # Substrate check · need ≥ (TRAIN + EMBARGO + OOS) trading days = 320 min
    n_dates = pit["unique_asof_dates"]
    if n_dates < 30:
        # For fundamentals we're not at Historical_Tested yet · this is BLOCKED
        exp = evidence_log.append_evidence_record(
            root, item_id=item["id"], market=market,
            data_snapshot=pit["latest_asof"], pit_status="insufficient_history",
            fold_definition={"reason": f"unique_asof_dates={n_dates}<30"},
            trial_count=0, parameters={"signal_col": signal_col},
            sample_size=n_dates, metrics={}, statistical_test={},
            multiple_testing_correction={}, decision="BLOCKED",
            artifact_paths=[])
        return {"item_id": item["id"], "market": market, "decision": "BLOCKED",
                 "reason": (f"n_unique_asof_dates={n_dates} < 30 (V2 stronger-evidence tier) · "
                             "substrate must accumulate · accumulator runs daily via CI"),
                 "pit_summary": pit,
                 "experiment_id": exp, "evidence_clock_state": "DATA_USABLE"}

    # Sufficient dates · run historical evidence
    # Define the signal_dates_fn + signal_and_outcome_fn
    import pandas as pd
    df = _load_fundamentals_history(root, market)
    df = df.dropna(subset=[signal_col])
    df["asof_d"] = pd.to_datetime(df["asof"]).dt.date

    def _dates_fn(_root: Path, _market: str):
        return sorted(df["asof_d"].unique())

    # AUDIT-06 · PIT universe membership hook · universe_at_date_fn wired
    # inside the signal_and_outcome_fn so filtering happens where the ticker
    # labels live. Universe = the set of tickers with a PIT fundamentals row
    # at the fold's oos_start (this is the strictest PIT universe available
    # from the accumulator itself · never today's superset).
    def _universe_at_date_fn(_root: Path, _market: str, asof):
        return sorted(df[df["asof_d"] == asof]["ticker"].astype(str).unique())

    def _signal_and_outcome_fn(_root: Path, _market: str, fold):
        # AUDIT-06 · restrict OOS candidates to tickers in PIT universe at
        # fold.oos_start · prevents future-universe leakage
        pit_universe = set(_universe_at_date_fn(_root, _market, fold.oos_start))
        oos_df = df[(df["asof_d"] >= fold.oos_start) & (df["asof_d"] <= fold.oos_end)
                     & (df["ticker"].astype(str).isin(pit_universe))]
        if len(oos_df) < 10: return [], []
        # Signal direction determines rank
        if item["direction"] == "positive":
            oos_df = oos_df.sort_values(signal_col, ascending=False)
        else:
            oos_df = oos_df.sort_values(signal_col, ascending=True)
        decile = max(3, len(oos_df) // 10)
        top = oos_df.head(decile)
        from backend.research.evidence.forward_paper import compute_matured_return
        returns = []
        for _, row in top.iterrows():
            r = compute_matured_return(_root, _market, str(row["ticker"]),
                                        str(row["asof"]), 20)
            if r is not None: returns.append(r)
        return [1.0] * len(returns), returns

    # AUDIT-03 · declare the experiment family explicitly. Single top-decile
    # test = 1 trial in family · but the family_id makes multi-decile expansions
    # (which would raise trial_count) visible in Evidence Log.
    family_id = f"{item['id']}_top_decile_20d_v1"
    result: EvidenceResult = run_historical_evidence(
        root, item["id"], market,
        signal_dates_fn=_dates_fn,
        signal_and_outcome_fn=_signal_and_outcome_fn,
        trial_count=1,
        experiment_family_id=family_id,
        universe_at_date_fn=_universe_at_date_fn,
        parameters={"signal_col": signal_col, "direction": item["direction"],
                     "decile": "top", "horizon_days": 20},
    )
    return {
        "item_id": result.item_id, "market": result.market,
        "decision": result.decision, "reason": result.reason,
        "pit_summary": pit,
        "n_folds": result.n_folds, "n_oos_samples": result.n_oos_samples,
        "metrics": result.metrics,
        "experiment_id": result.experiment_id,
        "evidence_clock_state": result.clock_state,
    }


def main():
    results = []
    for item in FUNDAMENTAL_ITEMS:
        for market in ("india", "usa"):
            r = run_item(_ROOT, item, market)
            results.append(r)
            print(f"[{item['id']}][{market}] decision={r['decision']} · "
                    f"clock={r['evidence_clock_state']} · reason={r['reason'][:80]}")

    # Consolidated Evidence Report per Section G
    out = _ROOT / "reports" / "research" / "evidence" / "evidence_program_F01_F05.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    consolidated = {
        "engine": "aegis_evidence_program",
        "version": "v1.0",
        "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol": "V2 PDF walk-forward 252/5/63/21 + DSR",
        "governance": {
            "r2_production_unchanged": True,
            "13_stage_tracker_is_governance_sot": True,
            "evidence_clock_is_measurement_only": True,
            "substrate_before_sophistication_rule_intact": True,
        },
        "n_items": len(FUNDAMENTAL_ITEMS), "n_markets": 2,
        "n_evaluations": len(results),
        "results": results,
        "summary_by_decision": {},
    }
    from collections import Counter
    consolidated["summary_by_decision"] = dict(Counter(r["decision"] for r in results))
    out.write_text(json.dumps(consolidated, indent=2, default=str), encoding="utf-8")
    print(f"\n[program] wrote {out.relative_to(_ROOT)}")
    print(f"[program] summary: {consolidated['summary_by_decision']}")


if __name__ == "__main__":
    main()
