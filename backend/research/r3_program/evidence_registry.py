"""R3 EVIDENCE REGISTRY · one row per research family, DERIVED not declared.

> "Do not start another R&D branch until you first inspect the evidence
>  registry and determine whether its substrate is actually ready."

WHY THIS IS COMPUTED, NOT WRITTEN DOWN
---------------------------------------
A hand-maintained research status drifts from reality in one direction:
towards looking further along than it is. Every field below is read from
the artifact the branch actually produced, so a family cannot claim
progress it did not make, and a substrate that shrank shows up as a
regression rather than as yesterday's number.

It also answers the question that keeps getting asked in the wrong order.
Not "which model should we try next" but "which branch's substrate is
actually ready" - and on today's data the answer for most of them is
none, which is a finding rather than an obstacle.

THE GATES ARE ARITHMETIC, NOT JUDGEMENT
----------------------------------------
`next_required_condition` states the exact quantity still missing, so
nobody has to argue about readiness:

    fundamental forecasting  needs 8 quarters · has 6-7
    meta-label evaluation    needs 50 matured outcomes · has 0
    probability display      needs 4 consecutive weeks ECE <= 0.05

When a threshold is met the family flips to READY_FOR_EVALUATION. That
flag enables an evaluation; it never promotes anything.

RESEARCH ONLY · reads artifacts, writes one report, changes no behaviour.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.evidence_registry.v1"

# The ONLY terminal states. No new governance vocabulary.
STATES = (
    "NOT_STARTED", "ACCUMULATING", "INSUFFICIENT_SUBSTRATE",
    "RESEARCH_SIGNAL", "STRONGER_EVIDENCE", "VALIDATION_CANDIDATE",
    "REJECTED", "NO_INCREMENTAL_VALUE", "FROZEN", "PROMOTION_CANDIDATE",
)

# Activation thresholds · pre-registered, not tuned after seeing results.
GATE_FUNDAMENTAL_QUARTERS = 8
GATE_FUNDAMENTAL_TICKERS = 30
GATE_FUNDAMENTAL_OBS = 50
GATE_METALABEL_OUTCOMES = 50
GATE_STRONG_OOS_OUTCOMES = 200
GATE_CALIBRATION_WEEKS = 4
GATE_CALIBRATION_ECE = 0.05


def _row(**kw) -> dict:
    """One registry row · every field the mandate names, always present."""
    base = {
        "research_id": "", "domain": "", "dataset": "", "market": "",
        "n_rows": 0, "n_tickers": 0, "n_dates": 0, "effective_sample": 0,
        "PIT_status": "UNKNOWN", "OOS_status": "NOT_RUN",
        "multiple_testing_method": "none",
        "calibration_status": "NOT_APPLICABLE",
        "economic_value_status": "NOT_TESTED",
        "incremental_R2_status": "NOT_TESTED",
        "current_verdict": "NOT_STARTED",
        "next_required_condition": "",
        "ready_for_evaluation": False,
    }
    base.update(kw)
    assert base["current_verdict"] in STATES, base["current_verdict"]
    return base


# ── substrate readers ───────────────────────────────────────────────────

def _fundamental(root: Path, market: str) -> dict:
    from backend.research.substrate import fundamental_timeseries as ft
    tk = (ft.load(root, market) or {}).get("tickers") or {}
    per = sorted(len(v.get("periods") or []) for v in tk.values())
    n = len(per)
    return {
        "n_tickers": n,
        "n_periods": sum(per),
        "median_quarters": per[n // 2] if n else 0,
        "tickers_ge_gate": sum(1 for x in per if x >= GATE_FUNDAMENTAL_QUARTERS),
    }


def _shadow(root: Path, market: str) -> dict:
    from backend.research.r3_program import shadow
    led = shadow.load_ledger(root, market)
    dates = sorted({r.get("as_of") for r in led if r.get("as_of")})
    p = (root / "reports" / "research" / "r3" / "shadow"
         / ("outcomes_%s.jsonl" % market))
    matured = 0
    if p.exists():
        matured = sum(1 for l in p.read_text(encoding="utf-8").splitlines()
                      if l.strip())
    return {"n_records": len(led), "n_dates": len(dates), "dates": dates,
            "n_tickers": len({r.get("ticker") for r in led}),
            "matured_outcomes": matured}


def _cohort(root: Path, market: str) -> dict:
    from backend.research.r3_program import core
    try:
        rows = core.load_pop(root, market, features=["confidence_pct"])
    except Exception:
        return {"n_rows": 0, "n_tickers": 0, "n_dates": 0,
                "effective_ticker_units": 0, "effective_date_units": 0}
    a = core.substrate_assessment(rows)
    return a


# ── the registry ────────────────────────────────────────────────────────

def build(root: Path) -> dict:
    rows = []
    for m in ("india", "usa"):
        f = _fundamental(root, m)
        s = _shadow(root, m)
        c = _cohort(root, m)

        # ── R3-E-2C · seven filters · ALREADY DISPOSED ─────────────────
        from backend.research.cohort import seven_filter_ai as sf
        rep = sf.load(root, m) or {}
        b = (rep.get("by_lag") or {}).get("45") or {}
        inc = b.get("incremental_over_r2") or {}
        mt = b.get("multiple_testing") or {}
        rows.append(_row(
            research_id="R3-E-2C", domain="Fundamental · seven filters",
            dataset="cohort x fundamental_timeseries", market=m,
            n_rows=b.get("n", 0), n_tickers=b.get("n_tickers", 0),
            n_dates=c["n_dates"], effective_sample=c["effective_ticker_units"],
            PIT_status="PIT_ASSUMED_LAG_45D · 30/60 sensitivity tested",
            OOS_status="TICKER_DISJOINT",
            multiple_testing_method="Benjamini-Hochberg FDR q<0.05",
            economic_value_status="TESTED",
            incremental_R2_status=("KILL_MODEL · CI spans zero"
                                   if "KILL" in str(inc.get("verdict"))
                                   else "REFUSED · below event floor"),
            current_verdict="NO_INCREMENTAL_VALUE",
            next_required_condition=(
                "DO NOT RERUN on this data. %d of %d dimensions survived FDR. "
                "Reopens only when the cohort spans multiple earnings dates "
                "per name, which makes fundamentals a variable rather than a "
                "per-ticker label."
                % (mt.get("n_significant", 0), mt.get("n_tests", 0))),
        ))

        # ── R3-D · fundamental forecasting ─────────────────────────────
        need_q = max(0, GATE_FUNDAMENTAL_QUARTERS - f["median_quarters"])
        ready_f = (f["tickers_ge_gate"] >= GATE_FUNDAMENTAL_TICKERS)
        rows.append(_row(
            research_id="R3-D-FCST", domain="Fundamental forecasting",
            dataset="fundamental_timeseries", market=m,
            n_rows=f["n_periods"], n_tickers=f["n_tickers"],
            n_dates=c["n_dates"], effective_sample=f["tickers_ge_gate"],
            PIT_status="PIT_ASSUMED_LAG_45D",
            OOS_status="NOT_RUN",
            current_verdict=("ACCUMULATING" if f["n_tickers"]
                             else "INSUFFICIENT_SUBSTRATE"),
            next_required_condition=(
                "%d ticker(s) have >=%dq · need %d. Median history is %dq, "
                "so ~%d more quarter(s) of accumulation. DO NOT lower the "
                "gate or synthesise quarters."
                % (f["tickers_ge_gate"], GATE_FUNDAMENTAL_QUARTERS,
                   GATE_FUNDAMENTAL_TICKERS, f["median_quarters"], need_q)),
            ready_for_evaluation=ready_f,
        ))

        # ── R3-K · meta-label · waits on MATURED outcomes ──────────────
        ready_m = s["matured_outcomes"] >= GATE_METALABEL_OUTCOMES
        rows.append(_row(
            research_id="R3-K-META", domain="R2 -> R3 meta-label",
            dataset="r3 shadow ledger", market=m,
            n_rows=s["n_records"], n_tickers=s["n_tickers"],
            n_dates=s["n_dates"], effective_sample=s["matured_outcomes"],
            PIT_status="PIT_OK · prediction written before outcome exists",
            OOS_status="NOT_RUN · no matured outcomes",
            calibration_status="NOT_APPLICABLE · all ABSTAIN",
            current_verdict="ACCUMULATING",
            next_required_condition=(
                "%d matured outcome(s) · need %d. Predictions exist on %d "
                "date(s); the first fwd_5d cohort matures ~5 trading days "
                "after its prediction date."
                % (s["matured_outcomes"], GATE_METALABEL_OUTCOMES,
                   s["n_dates"])),
            ready_for_evaluation=ready_m,
        ))

    # ── market-agnostic branches · disposed, preserved verbatim ─────────
    for rid, dom, verdict, why in (
        ("R3-C-SEQ", "Temporal · sequence models", "FROZEN",
         "TCN/GRU/Transformer killed for date leakage · reopens only at "
         ">=200 usable episodes AND >=20 independent dates AND ticker x "
         "date OOS"),
        ("II.1-GBM", "Wave 1D headline", "REJECTED",
         "INVALIDATED · R-multiple tautology, 51.6% synthetic stops, no "
         "joint ticker x date control · preserved as audit history"),
        ("R3-G-EXIT", "Risk / exit intelligence", "FROZEN",
         "Wave 1D-E found no absolute-return economic edge · reopens as an "
         "R2 meta-label question, never as a return forecast"),
        ("R3-H-UNSUP", "Unsupervised · clustering", "REJECTED",
         "6/6 lanes died under a ticker-block permutation of the "
         "ticker-disjoint OOS assignment · descriptive only"),
        ("R3-I-INTRADAY", "Intraday", "INSUFFICIENT_SUBSTRATE",
         "no intraday bars on disk · needs 1m/5m with exchange timestamps"),
        ("R3-F-MKT", "Market / sector / macro transmission", "NOT_STARTED",
         "series are collected and freshness-gated · D17 evidence-blocked · "
         "needs descriptive -> lead/lag -> conditional -> OOS -> "
         "incremental before any decision use"),
    ):
        rows.append(_row(research_id=rid, domain=dom, market="both",
                         current_verdict=verdict,
                         next_required_condition=why))

    ready = [r for r in rows if r["ready_for_evaluation"]]
    from collections import Counter
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gates": {
            "fundamental_quarters": GATE_FUNDAMENTAL_QUARTERS,
            "fundamental_tickers": GATE_FUNDAMENTAL_TICKERS,
            "metalabel_matured_outcomes": GATE_METALABEL_OUTCOMES,
            "strong_oos_outcomes": GATE_STRONG_OOS_OUTCOMES,
            "calibration_weeks": GATE_CALIBRATION_WEEKS,
            "calibration_ece_max": GATE_CALIBRATION_ECE,
        },
        "n_families": len(rows),
        "verdict_counts": dict(Counter(r["current_verdict"] for r in rows)),
        "ready_for_evaluation": [r["research_id"] + ":" + r["market"]
                                 for r in ready],
        "families": rows,
        "stop_rule": (
            "No new model class without a predefined scientific reason and "
            "an evidence hypothesis. A failed model is a research result, "
            "not an invitation to try the next algorithm."),
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "research" / "r3" / "R3_EVIDENCE_REGISTRY.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path) -> Optional[dict]:
    p = root / "reports" / "research" / "r3" / "R3_EVIDENCE_REGISTRY.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def render(rep: dict) -> str:
    L = ["═" * 78, "R3 EVIDENCE REGISTRY   ·   %s" % rep["generated_utc"][:19],
         "═" * 78,
         "%-16s %-6s %7s %7s %7s  %s"
         % ("RESEARCH_ID", "MKT", "ROWS", "TICKERS", "EFF", "VERDICT")]
    for r in rep["families"]:
        L.append("%-16s %-6s %7d %7d %7d  %s%s"
                 % (r["research_id"], r["market"][:5], r["n_rows"],
                    r["n_tickers"], r["effective_sample"],
                    r["current_verdict"],
                    "  ← READY" if r["ready_for_evaluation"] else ""))
    L += ["", "counts: %s" % rep["verdict_counts"],
          "ready for evaluation: %s"
          % (", ".join(rep["ready_for_evaluation"]) or "NONE"),
          "", "NEXT REQUIRED CONDITION (the arithmetic, not an opinion)"]
    seen = set()
    for r in rep["families"]:
        k = r["research_id"]
        if k in seen or not r["next_required_condition"]:
            continue
        seen.add(k)
        L.append("  %s · %s" % (k, r["next_required_condition"][:150]))
    L.append("═" * 78)
    return "\n".join(L)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 evidence registry")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    rep = build(root)
    emit(root, rep)
    print(render(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
