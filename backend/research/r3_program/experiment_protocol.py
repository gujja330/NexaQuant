"""Preregistered evaluation protocol for R3_EXPERIMENTAL_BASELINE_v1.

WHY PREREGISTRATION, HERE, MATTERS MORE THAN USUAL
---------------------------------------------------
The R3 programme already produced one result that had to be withdrawn:
a +1.57pp / AUC 0.6079 USA meta-label that turned out to describe two
consecutive mornings wearing 495 ticker names. The defence against
repeating that is writing down what counts as success BEFORE the
outcomes are known, and refusing to move the line afterwards.

THE DISTINCTION THIS FILE EXISTS TO PROTECT
--------------------------------------------
shadow_recommender can record decisions for every sealed snapshot back
to 2026-09-15. Those snapshots are genuinely point-in-time - written
each morning and never revised, so no future price touched the score.

But they were RECORDED today, when the outcomes already existed. That
makes them a point-in-time BACKTEST, not a prospective experiment. The
two are not the same evidence and must never be pooled:

  BACKTEST    as_of <= preregistration date · PIT inputs · outcomes
              already existed at record time · susceptible to the
              choice of policy having been made after seeing the period
  PROSPECTIVE as_of >  preregistration date · recorded before the
              outcome existed · the only segment that can support a
              claim of forward skill

Every metric must be reported for each segment separately. A combined
number is not reported at all, because the combined number is the one
that would be quoted.

WHAT A 90-DAY REVIEW IS NOT
----------------------------
It is not a promotion gate. If the prospective segment has fewer than
MIN_DATES_CONFIRMATORY date units, or horizons have not matured, the
protocol says EXTEND - it does not say decide anyway on what arrived.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROTOCOL_VERSION = "aegis.r3.experiment.protocol.v1"
ENGINE_UNDER_TEST = "R3_EXPERIMENTAL_BASELINE_v1"

# Preregistration date · the boundary between backtest and prospective.
PREREGISTERED_ON = "2026-10-28"
OBSERVATION_DAYS = 90

MIN_DATES_CONFIRMATORY = 20
HORIZONS = (5, 10, 20)

# Stated as an ASSUMPTION. No fill of this strategy has ever occurred,
# so this is not a measurement and is never to be presented as one.
ASSUMED_ROUNDTRIP_COST_PCT = 0.20
COST_GRID_PCT = (0.0, 0.10, 0.20, 0.50)

BENCHMARK = {"india": "^NSEI", "usa": "^GSPC"}


def observation_end(start: str = PREREGISTERED_ON,
                    days: int = OBSERVATION_DAYS) -> str:
    return (date.fromisoformat(start) + timedelta(days=days)).isoformat()


PROTOCOL = {
    "protocol_version": PROTOCOL_VERSION,
    "engine_under_test": ENGINE_UNDER_TEST,
    "status": "RESEARCH ONLY · NOT A PROMOTION GATE",

    "policy": {
        "description": ("per-date cross-sectional rank on ensemble_score "
                        "from the sealed r2_scores snapshot"),
        "take": "top 10% of that date's universe",
        "avoid": "bottom 10% of that date's universe",
        "abstain": "everything else, and every failure path",
        "fitted_parameters": 0,
        "honest_limitation": (
            "this RE-RANKS R2's own score. A positive result shows that "
            "score is usable for selection. It does NOT demonstrate "
            "independent R3 skill and must never be reported as such."),
    },

    "segments": {
        "rule": ("decided by whether the OUTCOME existed at record time, "
                 "not by a fixed calendar cut · as_of >= the date the row "
                 "was written is prospective"),
        "stamped": ("frozen into each record as `evidence_segment` at "
                    "write time and never recomputed · recomputing later "
                    "would convert backtest rows into prospective ones as "
                    "the calendar moves"),
        "backtest": {
            "definition": "as_of < the date the record was written",
            "inputs": "point-in-time · sealed snapshots, never revised",
            "caveat": ("outcomes already existed when these rows were "
                       "recorded · supports feasibility, not forward skill"),
        },
        "prospective": {
            "definition": "as_of >= the date the record was written",
            "window": {"start": PREREGISTERED_ON,
                       "end": observation_end(),
                       "days": OBSERVATION_DAYS},
            "caveat": "the only segment that can support a skill claim",
        },
        "pooling": "FORBIDDEN · report the two separately, always",
    },

    "universe": {
        "source": "history/<market>/<date>/r2_scores.parquet",
        "eligibility": "every ticker present in that date's sealed snapshot",
        "min_universe": 30,
        "exclusions": ("snapshot missing, malformed, or universe below "
                       "minimum · recorded as ABSTAIN with a reason"),
    },

    "schedule": {
        "decision": "one decision per ticker per sealed snapshot date",
        "resolution": "horizons mature independently and are appended once",
    },

    "horizons_trading_days": list(HORIZONS),
    "benchmark": BENCHMARK,

    "costs": {
        "assumed_roundtrip_pct": ASSUMED_ROUNDTRIP_COST_PCT,
        "grid_pct": list(COST_GRID_PCT),
        "is_an_assumption": True,
        "note": "no actual fills exist · never present this as measured",
    },

    "missing_data_policy": {
        "immature_horizon": "ABSENT · never 0.0",
        "no_bars": "excluded and counted, never imputed",
        "no_reference_price": "risk-flagged on the record",
        "duplicate_keys": "forbidden · (as_of, ticker, horizon) is unique",
    },

    "metrics": [
        "take_coverage_pct", "abstention_rate_pct",
        "win_rate_pct (return > 0 at the horizon)",
        "mean_return_pct", "median_return_pct",
        "benchmark_relative_return_pct",
        "net_return_at_each_cost_in_grid",
        "max_drawdown_pct", "max_adverse_excursion_pct",
        "by_market", "by_horizon", "by_action",
        "n_rows", "n_effective_date_units",
        "ci95_date_block_bootstrap",
        "n_excluded_and_why",
    ],

    "inference_rules": {
        "unit_of_analysis": (
            "DATE, not row · names admitted on one morning share that "
            "morning's market move"),
        "overlapping_returns": (
            "a 20d horizon sampled daily overlaps ~20x · naive t is "
            "inflated by roughly sqrt(20) · use date-block bootstrap or "
            "non-overlapping subsamples"),
        "multiple_comparisons": (
            "3 horizons x 2 markets x 2 actions · apply BH-FDR across the "
            "family, report the adjusted result as primary"),
        "survivorship": (
            "the snapshot universe is fixed at decision time, so the "
            "decision set is survivorship-free · the BARS used to resolve "
            "are not, and delisted names must be counted as excluded"),
        "selection_effects": (
            "the policy was specified before this protocol was written "
            "but AFTER rank_separation examined the same sealed period · "
            "the backtest segment is therefore contaminated by that look "
            "and only the prospective segment is clean"),
        "walk_forward": (
            "no parameter is fitted, so there is nothing to re-fit · if a "
            "future version fits anything, it must be fitted and evaluated "
            "on disjoint periods"),
        "no_tuning_on_evaluation_outcomes": (
            "if the policy changes, the engine version changes, the "
            "decision_id changes, and the 90-day clock restarts"),
    },

    "minimum_sample": {
        "dates_for_confirmatory": MIN_DATES_CONFIRMATORY,
        "below_floor": "EXPLORATORY · no inference reported",
        "india_status_at_preregistration": "34 sealed dates (backtest)",
        "usa_status_at_preregistration": "14 sealed dates · EXPLORATORY",
        "usa_rule": ("record from day one so the clock accumulates, but "
                     "USA carries no confirmatory weight until it reaches "
                     "%d prospective date units" % MIN_DATES_CONFIRMATORY),
    },

    "review_rules": {
        "at_90_days": "REVIEW, not promotion",
        "extend_if": [
            "prospective date units < %d" % MIN_DATES_CONFIRMATORY,
            "20d horizon not matured for the bulk of the window",
            "confidence intervals straddle zero",
        ],
        "promotion": ("out of scope for this protocol · R3 remains "
                      "research-only regardless of outcome"),
    },
}


def protocol_hash(p: dict = None) -> str:
    """Changing the protocol changes this · preregistration is checkable."""
    blob = json.dumps(p if p is not None else PROTOCOL, sort_keys=True,
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def artifact_path(root: Path) -> Path:
    return (Path(root) / "reports" / "research" / "r3" / "experiment"
            / "protocol.json")


def emit(root: Path) -> Path:
    p = artifact_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(PROTOCOL)
    payload["preregistered_on"] = PREREGISTERED_ON
    payload["protocol_hash"] = protocol_hash()
    payload["emitted_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    p.write_text(json.dumps(payload, indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def segment_of(as_of: str, recorded_on: str = None) -> str:
    """Which evidence segment a decision belongs to.

    CEO 2026-10-28 · CORRECTED. This first compared as_of against a fixed
    preregistration date, which asked the wrong question. What decides the
    segment is whether the OUTCOME already existed when the row was
    written, not where the date falls against a constant.

    A snapshot sealed this morning has no 5/10/20-day outcome yet, so
    recording it today is genuinely prospective. One from 2026-09-15 has
    all three resolved, so recording it today is a backtest however
    point-in-time its inputs were.

    Delegates to shadow_recommender.evidence_segment so there is one
    definition rather than two that can drift apart.
    """
    from backend.research.r3_program.shadow_recommender import (
        evidence_segment as _seg)
    return _seg(as_of, recorded_on)


if __name__ == "__main__":
    import sys
    out = emit(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print("protocol %s · hash %s -> %s"
          % (PROTOCOL_VERSION, protocol_hash(), out))
