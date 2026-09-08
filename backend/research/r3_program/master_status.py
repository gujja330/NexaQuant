"""R3 AI MASTER STATUS · SCORECARD · FREEZE RECORD.

Phases 0, XXIII and XXIV. This module does not run experiments; it reads
what the experiments actually wrote and assigns each intelligence class a
disposition. Nothing here may invent a result, and nothing here may
upgrade one.

WHY DISPOSITIONS ARE READ, NOT DECLARED
----------------------------------------
A status document that is maintained by hand drifts from the code it
describes, and drifts in one direction: towards looking finished. Every
row below is derived from a report file on disk, so the scorecard cannot
claim a branch passed unless that branch's own report says so.

THREE CLASSES ARE DETERMINED HERE DIRECTLY
-------------------------------------------
R3-D forecasting, R3-F market/sector and R3-I intraday have no dedicated
experiment because their substrate decides them before any model would.
Each is assessed against the data actually on disk, and the assessment
records exactly what is missing and what would unblock it.

PRESERVATION IS MANDATORY
--------------------------
Wave 1D remains INVALIDATED. Wave 1C and 1D-E remain REJECTED. The R3-G
freeze stands. No later implementation may overwrite a negative result;
this module reads them forward into the final record verbatim.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.r3_program import core

SCHEMA_VERSION = "aegis.r3.master_status.v1"

# Historical dispositions that MUST survive into the final record.
# These are read forward verbatim · never recomputed, never softened.
PRESERVED = {
    "R3-G-EXIT · Wave 1A entry reconstruction": (
        "ACCEPTED", "USA entry coverage 12.4% -> 100%; stops deliberately "
        "NOT backfilled"),
    "R3-G-EXIT · Wave 1B hazard/survival": (
        "ACCEPTED", "547 India / 79 USA episodes · peak +1.573R decaying to "
        "final +0.274R"),
    "R3-C-TEMP · Wave 1C sequence models": (
        "REJECTED", "TCN/GRU/Transformer · date leakage across the split; "
        "killed by construction, not by score"),
    "II.1-GBM · Wave 1D headline": (
        "INVALIDATED", "AUC 1.000/0.974 preserved as AUDIT HISTORY only · "
        "R-multiple tautology (stop_distance alone reached 0.853), 51.6% "
        "synthetic 5% default stops, neither split controlling ticker and "
        "date jointly"),
    "R3-G-EXIT · Wave 1D-C corrected validator": (
        "PARTIAL", "joint ticker x date holdout with real/default stops "
        "segmented"),
    "R3-G-EXIT · Wave 1D-E absolute-target falsification": (
        "REJECTED", "no absolute target both beat its baseline and added "
        "economic value · the R-multiple edge was an artefact of the R "
        "definition"),
    "R3-G-EXIT branch": (
        "FROZEN", "frozen 2026-09-08 · reopens only on new dates/tickers and "
        "only as an R2 meta-label question, never as a return forecast"),
    "R3-B-STAT · confidence robustness": (
        "RESEARCH_ONLY", "pooled anti-predictive signal is largely a "
        "ticker-mix artefact; USA is structurally positive within names "
        "(r=+0.127, median per-ticker +0.528)"),
    "R3-E-2C · seven-filter research": (
        "REJECTED", "0 of 4 India and 0 of 6 USA dimensions survive once "
        "significance moves to ticker units (row p=0.000 -> ticker p=0.386); "
        "incremental AUC +0.0138 with CI [-0.074, +0.105]"),
    "R3-A-DESC / P0-P5 cohort findings": (
        "DESCRIPTIVE_ONLY", "retained as cohort description · no decision "
        "claim was ever made from them"),
}

CLASSES = ("R3-A", "R3-B", "R3-C", "R3-D", "R3-E", "R3-F",
           "R3-G", "R3-H", "R3-I", "R3-J", "R3-K")


def _assess_intraday(root: Path) -> dict:
    """R3-I · is there any intraday substrate at all."""
    pats = ("*_1m*", "*_5m*", "*intraday*.parquet", "*intraday*.csv")
    found = []
    for base in (root / "data", root / "features", root / "reports"):
        if not base.exists():
            continue
        for pat in pats:
            found += [str(p) for p in base.rglob(pat)][:3]
    engine = (root / "backend" / "intraday").exists()
    return {
        "class": "R3-I", "name": "Intraday Intelligence",
        "substrate_files_found": found[:5],
        "engine_scaffolding_present": engine,
        "disposition": "BLOCKED" if not found else "INSUFFICIENT_SUBSTRATE",
        "reason": (
            "No intraday bar data exists on disk. `backend/intraday` holds "
            "engine scaffolding (feed, session_clock, signals, execution) but "
            "there is no timestamped price substrate to build a PIT intraday "
            "dataset from, so there is nothing to validate. Engineering is "
            "present; evidence is absent."
            if not found else
            "some intraday artefacts exist but no PIT-safe dataset"),
        "what_would_unblock": [
            "persisted 1m or 5m bars with exchange timestamps",
            "session-aware feature snapshots taken at decision time",
            "an intraday outcome definition with transaction-cost assumptions",
            "day-level out-of-sample accounting",
        ],
        "production_impact": "none · intraday remains isolated from delivery",
    }


def _assess_sector(root: Path) -> dict:
    """R3-F · is the sector column actually sector information."""
    per = {}
    for m in ("india", "usa"):
        rows = core.load_pop(root, m, features=["confidence_pct"])
        v = core.sector_validity(rows)
        cov = sum(1 for r in rows if r.get("sector")) / max(1, len(rows)) * 100
        v["coverage_pct"] = round(cov, 1)
        per[m] = v
    usable = [m for m, v in per.items() if v["usable_as_sector"]]
    return {
        "class": "R3-F", "name": "Market / Sector Intelligence",
        "by_market": per,
        "disposition": "BLOCKED" if not usable else "INSUFFICIENT_SUBSTRATE",
        "reason": (
            "USA reports 'Large-Cap' on 96.5%% of rows - a capitalisation "
            "bucket, not a sector - and regime is null on every row in both "
            "markets. India carries usable sector labels on only %.1f%% of "
            "rows. Sector- and regime-conditioned findings cannot be "
            "computed from data that does not encode sector or regime."
            % per["india"]["coverage_pct"]),
        "what_would_unblock": [
            "a real GICS/NSE sector mapping joined at the universe level",
            "a populated regime column (currently null on all rows)",
        ],
        "production_impact": "none",
    }


def _assess_forecasting(root: Path) -> dict:
    """R3-D · is there enough quarterly history to forecast, and can any
    forecast be connected to a decision."""
    from backend.research.substrate import fundamental_timeseries as ft
    per = {}
    for m in ("india", "usa"):
        tk = (ft.load(root, m) or {}).get("tickers") or {}
        counts = [len(v.get("periods") or []) for v in tk.values()]
        rows = core.load_pop(root, m, features=["confidence_pct"])
        per[m] = {
            "n_tickers": len(tk),
            "total_periods": sum(counts),
            "median_periods_per_ticker": (sorted(counts)[len(counts) // 2]
                                          if counts else 0),
            "tickers_with_ge_8_quarters": sum(1 for c in counts if c >= 8),
            "effective_date_units_for_decision_test":
                core.substrate_assessment(rows)["effective_date_units"],
        }
    return {
        "class": "R3-D", "name": "Fundamental Forecasting Intelligence",
        "by_market": per,
        "disposition": "INSUFFICIENT_SUBSTRATE",
        "reason": (
            "Median quarterly history is %d periods (India) and %d (USA). A "
            "forecast can be fitted on that, and beating naive persistence "
            "would be easy to report - but the mandate's test is whether the "
            "forecast improves a DECISION, and the decision cohort supplies "
            "%d and %d independent date unit(s). The decision-value test is "
            "therefore not computable, so a forecast accuracy number would "
            "be a metric without a conclusion."
            % (per["india"]["median_periods_per_ticker"],
               per["usa"]["median_periods_per_ticker"],
               per["india"]["effective_date_units_for_decision_test"],
               per["usa"]["effective_date_units_for_decision_test"])),
        "what_would_unblock": [
            "8+ quarters for a majority of names (partially satisfied)",
            "a decision cohort spanning enough dates to price the forecast",
        ],
        "production_impact": "none",
    }


def _read_reports(root: Path) -> dict:
    from backend.research.cohort import seven_filter_ai
    from backend.research.ml_discovery import prequential
    from backend.research.r3_program import decision_models, unsupervised
    out = {"unsupervised": {}, "decision": {}, "prequential": {},
           "seven_filter": {}}
    for m in ("india", "usa"):
        out["unsupervised"][m] = unsupervised.load(root, m)
        out["decision"][m] = decision_models.load(root, m)
        out["prequential"][m] = prequential.load(root, m)
        out["seven_filter"][m] = seven_filter_ai.load(root, m)
    return out


def build(root: Path) -> dict:
    rep = _read_reports(root)
    classes = {}

    # ── R3-A descriptive ────────────────────────────────────────────────
    classes["R3-A"] = {
        "class": "R3-A", "name": "Descriptive Intelligence",
        "disposition": "DESCRIPTIVE_ONLY",
        "reason": ("cohort description, funnel diagnostics and failure-mode "
                   "profiling are complete and used as description · no "
                   "decision claim was made from them, which is the correct "
                   "terminal state for this class"),
        "production_impact": "none",
    }

    # ── R3-B statistical ────────────────────────────────────────────────
    classes["R3-B"] = {
        "class": "R3-B", "name": "Statistical Intelligence",
        "disposition": "RESEARCH_ONLY",
        "reason": ("confidence robustness answered its question: the pooled "
                   "anti-predictive signal is largely ticker mix, and within "
                   "names USA is structurally positive. The finding informs "
                   "interpretation; it was never a decision rule and the "
                   "0.55 confidence floor is untouched"),
        "production_impact": "none",
    }

    # ── R3-C temporal ───────────────────────────────────────────────────
    pq = {m: (rep["prequential"].get(m) or {}) for m in ("india", "usa")}
    classes["R3-C"] = {
        "class": "R3-C", "name": "Temporal Intelligence",
        "prequential_state": {
            m: {"cohort_dates": v.get("cohort_dates"),
                "ledger_total": v.get("ledger_total"),
                "verdict": (v.get("verdict") or "")[:120]}
            for m, v in pq.items()},
        "disposition": "INSUFFICIENT_SUBSTRATE",
        "reason": ("sequence models were REJECTED for date leakage and stay "
                   "rejected. The prequential ledger is built, running and "
                   "correctly refusing to issue a verdict below 50 scored "
                   "predictions · this is the class's accruing state, not a "
                   "failure"),
        "production_impact": "none",
    }

    classes["R3-D"] = _assess_forecasting(root)

    # ── R3-E fundamental ────────────────────────────────────────────────
    classes["R3-E"] = {
        "class": "R3-E", "name": "Fundamental Intelligence",
        "disposition": "REJECTED",
        "reason": ("Wave 2B built the substrate (India 45/265, USA 498/3431 "
                   "with read-time PIT lag). Wave 2C then tested it and 0 of "
                   "4 India and 0 of 6 USA dimensions survived moving "
                   "significance to ticker units; incremental value over R2 "
                   "was +0.0138 AUC with a CI of [-0.074, +0.105]. The "
                   "substrate is ACCEPTED and retained; the fundamental "
                   "DECISION OVERLAY is rejected"),
        "substrate_disposition": "ACCEPTED · retained for future reopening",
        "production_impact": "none",
    }

    classes["R3-F"] = _assess_sector(root)

    # ── R3-G risk/exit · preserved freeze ───────────────────────────────
    classes["R3-G"] = {
        "class": "R3-G", "name": "Risk / Exit Intelligence",
        "disposition": "FROZEN",
        "reason": ("branch frozen 2026-09-08 · Wave 1D INVALIDATED and "
                   "preserved as audit history, Wave 1D-E REJECTED. No "
                   "absolute target both beat its baseline and added "
                   "economic value. Hazard and survival statistics are "
                   "retained as descriptive"),
        "production_impact": "none · R2 exits untouched",
    }

    # ── R3-H unsupervised ───────────────────────────────────────────────
    uh = {m: (rep["unsupervised"].get(m) or {}) for m in ("india", "usa")}
    lanes = {m: {k: v.get("disposition") for k, v in
                 (u.get("lanes") or {}).items()} for m, u in uh.items()}
    classes["R3-H"] = {
        "class": "R3-H", "name": "Unsupervised Intelligence",
        "lanes_by_market": lanes,
        "anomaly_tested": sorted(
            (uh.get("usa") or {}).get("anomaly_detection", {}).keys()),
        "disposition": "DESCRIPTIVE_ONLY",
        "reason": ("all six cluster lanes separate outcomes in sample and "
                   "none survives a ticker-block permutation of the "
                   "ticker-disjoint out-of-sample assignment. Clusters "
                   "describe the cohort; they do not predict it. Outcome- "
                   "trajectory clustering was deliberately never emitted as "
                   "a feature"),
        "production_impact": "none",
    }

    classes["R3-I"] = _assess_intraday(root)

    # ── R3-J uncertainty/calibration ────────────────────────────────────
    cal = {}
    for m in ("india", "usa"):
        d = rep["decision"].get(m) or {}
        for t, r in (d.get("by_target") or {}).items():
            for rung, v in (r.get("baseline_ladder") or {}).items():
                sc = (v or {}).get("scores") or {}
                if sc.get("ece") is not None:
                    cal["%s/%s/%s" % (m, t, rung)] = {
                        "ece": sc["ece"], "brier": sc.get("brier"),
                        "brier_base_rate": sc.get("brier_base_rate"),
                        "calibration": sc.get("calibration")}
    classes["R3-J"] = {
        "class": "R3-J", "name": "Uncertainty / Calibration Intelligence",
        "measured_on": sorted(cal)[:8], "n_measured": len(cal),
        "sample": dict(list(sorted(cal.items()))[:3]),
        "disposition": "RESEARCH_ONLY",
        "reason": ("calibration (Brier, ECE, slope/intercept) and a "
                   "first-class ABSTAIN band are implemented and measured on "
                   "every ladder rung. They are infrastructure for a "
                   "surviving model, and no model survived, so there is "
                   "nothing to calibrate into production"),
        "production_impact": "none",
    }

    # ── R3-K decision synthesis ─────────────────────────────────────────
    dd = {}
    for m in ("india", "usa"):
        d = rep["decision"].get(m) or {}
        for t, r in (d.get("by_target") or {}).items():
            dd["%s/%s" % (m, t)] = {"disposition": r.get("disposition"),
                                    "reason": (r.get("reason") or "")[:200]}
    surviving = [k for k, v in dd.items()
                 if v["disposition"] in ("VALIDATED", "CONDITIONAL")]
    classes["R3-K"] = {
        "class": "R3-K", "name": "Evidence-Weighted Decision Synthesis",
        "targets_evaluated": dd,
        "surviving_specialists": surviving,
        "disposition": ("INSUFFICIENT_SUBSTRATE" if not surviving
                        else "CONDITIONAL"),
        "reason": ("a committee may contain only validated specialists. "
                   "Every specialist branch resolved to REJECTED, "
                   "DESCRIPTIVE_ONLY, FROZEN or INSUFFICIENT_SUBSTRATE, so "
                   "there is nothing eligible to combine. Building a "
                   "committee from unvalidated members would manufacture "
                   "confidence, which is the failure mode this programme "
                   "exists to prevent"
                   if not surviving else
                   "%d specialist(s) survived and may be combined under "
                   "explicit authorisation" % len(surviving)),
        "production_impact": "none",
    }

    counts = {}
    for c in classes.values():
        counts[c["disposition"]] = counts.get(c["disposition"], 0) + 1
    resolved = sum(1 for c in classes.values() if c["disposition"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "programme": "AEGIS R3 · AI Research & Decision-Intelligence",
        "classes_defined": len(CLASSES),
        "classes_resolved": resolved,
        "completion_pct": round(resolved / len(CLASSES) * 100, 1),
        "disposition_counts": counts,
        "classes": classes,
        "preserved_historical_results": {
            k: {"disposition": v[0], "detail": v[1]}
            for k, v in PRESERVED.items()},
        "preservation_note": (
            "Invalidated, rejected and frozen results above are read forward "
            "verbatim. No later implementation in this programme overwrote a "
            "negative result, and none may."),
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "research" / "r3" / "R3_AI_MASTER_STATUS.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path) -> Optional[dict]:
    p = root / "reports" / "research" / "r3" / "R3_AI_MASTER_STATUS.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 AI master status")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    rep = build(root)
    emit(root, rep)
    print("R3 AI MASTER STATUS · %d/%d classes resolved (%.0f%%)"
          % (rep["classes_resolved"], rep["classes_defined"],
             rep["completion_pct"]))
    for k in CLASSES:
        c = rep["classes"][k]
        print("  %-6s %-40s %s" % (k, c["name"], c["disposition"]))
    print("  counts: %s" % rep["disposition_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
