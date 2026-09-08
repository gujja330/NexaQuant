"""ML DISCOVERY v1 · EFFECTIVE-SAMPLE GATE · CEO 2026-09-08.

> "Don't let row count fool the model ... observational rows != independent
>  evidence."

WHY THIS GATE EXISTS
--------------------
India's cohort reports 456 mature fwd_10d observations. Those come from
37 distinct tickers over 15 trading days - a mean of 12.3 rows per ticker
against a 10-day forward window, so the same trade is counted roughly ten
times. The earlier "61 observations, 0% winners" finding turned out to be
six tickers, with ITC (29) and IRCTC (20) supplying 80% of it.

A model fitted on 456 rows would believe it had 456 independent examples.
It has about 37.

HOW EFFECTIVE UNITS ARE COUNTED
-------------------------------
Overlapping forward windows are the problem, so the count is:

    per ticker: floor(span_of_prediction_dates / forward_horizon), min 1
    effective  = sum over tickers

One ticker observed across a 15-day span with a 10-day horizon
contributes 1, not 15 - a second window would run past the span and
overlap the first. This is deliberately conservative: it is the number a
reader should be given before any importance chart.

THE GATES ARE ENGINEERING GATES
-------------------------------
> "I'd make the minimums configurable rather than pretending they are
>  AEGIS governance thresholds."

MIN_EFFECTIVE_UNITS / MIN_PREDICTION_DAYS / MIN_WALK_FORWARD_FOLDS are
ML-discovery engineering minimums. They do not replace the PDF's evidence
tiers or promotion gates, and passing them proves nothing about an edge.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.effective_sample.v1"

# Engineering minimums · configurable, NOT governance thresholds.
MIN_EFFECTIVE_UNITS = 50
MIN_PREDICTION_DAYS = 30
MIN_WALK_FORWARD_FOLDS = 3
EMBARGO_DAYS = 5
FORWARD_HORIZON = 10

# The three honest outcomes.
TIME_VALIDATED = "TIME_VALIDATED"
CROSS_SECTIONAL_HYPOTHESIS = "CROSS_SECTIONAL_HYPOTHESIS"
INSUFFICIENT_SUBSTRATE = "INSUFFICIENT_SUBSTRATE"


def _d(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def measure(rows: list, horizon_days: int = FORWARD_HORIZON) -> dict:
    """Everything the CEO asked the gate to report."""
    tick = Counter(str(r.get("ticker") or "") for r in rows)
    tick.pop("", None)
    days = sorted({d for d in (_d(r.get("prediction_date")) for r in rows) if d})

    per_ticker_dates = {}
    for r in rows:
        t = str(r.get("ticker") or "")
        d = _d(r.get("prediction_date"))
        if t and d:
            per_ticker_dates.setdefault(t, []).append(d)

    # FLOOR, not ceil. A ticker observed across a 15-day span with a 10-day
    # forward window yields ONE non-overlapping block, not two: the second
    # window would run past the span and overlap the first. Using ceil
    # scored India at 70 effective units and let it through a 50-unit gate
    # that it should fail - the very error this module exists to prevent.
    blocks = 0
    for t, ds in per_ticker_dates.items():
        span = (max(ds) - min(ds)).days + 1
        blocks += max(1, span // max(1, horizon_days))

    counts = sorted(tick.values())
    return {
        "n_rows": len(rows),
        "n_unique_tickers": len(tick),
        "n_prediction_dates": len(days),
        "date_range": [days[0].isoformat(), days[-1].isoformat()] if days else [],
        "max_obs_per_ticker": max(counts) if counts else 0,
        "median_obs_per_ticker": counts[len(counts) // 2] if counts else 0,
        "mean_obs_per_ticker": round(len(rows) / max(1, len(tick)), 2),
        "forward_horizon_days": horizon_days,
        "non_overlapping_forward_blocks": blocks,
        "effective_units": blocks,
        "row_to_effective_ratio": round(len(rows) / max(1, blocks), 2),
    }


def verdict(m: dict,
            min_units: int = MIN_EFFECTIVE_UNITS,
            min_days: int = MIN_PREDICTION_DAYS,
            min_folds: int = MIN_WALK_FORWARD_FOLDS,
            embargo: int = EMBARGO_DAYS) -> dict:
    """Refuse, or downgrade EXPLICITLY · never silently.

    > "The runner must refuse rather than silently downgrade the
    >  methodology."
    """
    reasons, blocking = [], []

    if m["effective_units"] < min_units:
        blocking.append(
            "effective_units %d < %d · %d rows from %d tickers over %d dates "
            "collapse to %d independent blocks at a %dd horizon"
            % (m["effective_units"], min_units, m["n_rows"],
               m["n_unique_tickers"], m["n_prediction_dates"],
               m["effective_units"], m["forward_horizon_days"]))

    # Temporal depth must cover folds plus embargo plus one horizon.
    needed = min_folds * (embargo + m["forward_horizon_days"])
    time_ok = m["n_prediction_dates"] >= min_days and \
        m["n_prediction_dates"] >= needed
    if not time_ok:
        reasons.append(
            "prediction dates %d < required %d (min_days %d · %d folds x "
            "(embargo %d + horizon %d)) · walk-forward not constructible"
            % (m["n_prediction_dates"], max(min_days, needed), min_days,
               min_folds, embargo, m["forward_horizon_days"]))

    if blocking:
        v = INSUFFICIENT_SUBSTRATE
    elif not time_ok:
        v = CROSS_SECTIONAL_HYPOTHESIS
    else:
        v = TIME_VALIDATED

    return {
        "verdict": v,
        "may_fit": v != INSUFFICIENT_SUBSTRATE,
        "time_validated": v == TIME_VALIDATED,
        "blocking_reasons": blocking,
        "downgrade_reasons": reasons,
        "gates": {"MIN_EFFECTIVE_UNITS": min_units,
                  "MIN_PREDICTION_DAYS": min_days,
                  "MIN_WALK_FORWARD_FOLDS": min_folds,
                  "EMBARGO_DAYS": embargo,
                  "FORWARD_HORIZON": m["forward_horizon_days"]},
        "gate_note": ("ML-discovery ENGINEERING gates · they do not replace "
                      "AEGIS evidence tiers or promotion gates, and passing "
                      "them proves nothing about an edge"),
        "measurement": m,
    }


def assess(rows: list, horizon_days: int = FORWARD_HORIZON, **kw) -> dict:
    return verdict(measure(rows, horizon_days), **kw)
