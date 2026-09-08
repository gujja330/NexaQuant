"""ML DISCOVERY v1 · SPLITS · CEO 2026-09-08.

Two split strategies, and the runner must say which one it used.

WALK-FORWARD WITH EMBARGO · the only time-valid option
------------------------------------------------------
Delegates to `backend.research.r3.tier1_gbm.walk_forward_folds`, which
already implements train-strictly-in-the-past with an embargo gap. It is
not reimplemented here: a second definition of "what is a valid fold"
would eventually disagree with the first, and this codebase has been
bitten by exactly that.

GROUPED-BY-TICKER · cross-sectional ONLY
-----------------------------------------
When temporal depth is insufficient, the runner may still ask "which
features separate winners from losers WITHIN a cross-section". For that,
folds must be grouped by ticker so the same name never appears in both
train and test - otherwise a model memorises ITC and reports it as skill.

This split proves NOTHING about persistence through time. Any result from
it is CROSS_SECTIONAL_HYPOTHESIS and must be labelled so.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.splits.v1"

WALK_FORWARD = "WALK_FORWARD_EMBARGO"
GROUPED_TICKER = "GROUPED_BY_TICKER_CROSS_SECTIONAL"


def _d(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def walk_forward(rows: list, n_folds: int = 3, embargo_days: int = 5) -> list:
    """(train_idx, test_idx) using the R3 embargoed splitter."""
    from backend.research.r3.tier1_gbm import walk_forward_folds
    dates = [_d(r.get("prediction_date")) for r in rows]
    if any(d is None for d in dates):
        return []
    try:
        folds = walk_forward_folds(dates, n_folds=n_folds,
                                   embargo_days=embargo_days)
    except Exception:
        return []
    return list(folds or [])


def grouped_by_ticker(rows: list, n_folds: int = 5) -> list:
    """Deterministic ticker-disjoint folds · no shuffling, no seed drift.

    Tickers are assigned round-robin over their sorted order, so the same
    cohort always yields the same folds and a rerun cannot quietly change
    an importance ranking.
    """
    tickers = sorted({str(r.get("ticker") or "") for r in rows} - {""})
    if len(tickers) < n_folds:
        return []
    assign = {t: i % n_folds for i, t in enumerate(tickers)}
    folds = []
    for k in range(n_folds):
        tr = [i for i, r in enumerate(rows)
              if assign.get(str(r.get("ticker") or ""), -1) not in (k, -1)]
        te = [i for i, r in enumerate(rows)
              if assign.get(str(r.get("ticker") or ""), -1) == k]
        if tr and te:
            folds.append((tr, te))
    return folds


def describe(kind: str) -> str:
    if kind == WALK_FORWARD:
        return ("train strictly in the past with an embargo gap · the only "
                "split that supports a claim about persistence through time")
    return ("ticker-disjoint folds within the available cross-section · "
            "prevents memorising a name, proves NOTHING about time")
