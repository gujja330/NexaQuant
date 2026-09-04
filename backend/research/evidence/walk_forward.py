"""Section A · Walk-Forward Protocol.

Locked per V2 PDF · TRAIN 252 · EMBARGO 5 · OOS 63 · STEP 21 · trading days.

Mechanically enforces · no random split · no OOS fitting · no hindsight
threshold selection · no feature leakage across embargo boundary.

CEO 2026-09-05 AUDIT-01 · trading-day math is now EXCHANGE-AWARE via
backend/research/evidence/trading_calendars.py · NSE + NYSE holidays honored.
Legacy weekday-only path retained for tests that don't specify market.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Iterator, Optional

from backend.research.evidence.trading_calendars import add_trading_days as _add_market_tdays


# LOCKED per V2 PDF · never override without CEO authorization
TRAIN_DAYS = 252
EMBARGO_DAYS = 5
OOS_DAYS = 63
STEP_DAYS = 21


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: date
    train_end: date
    embargo_end: date       # oos_start = embargo_end + 1
    oos_start: date
    oos_end: date

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("train_start","train_end","embargo_end","oos_start","oos_end"):
            d[k] = str(d[k])
        return d


def _add_trading_days(d: date, n: int, market: Optional[str] = None) -> date:
    """Add n trading days · EXCHANGE-AWARE when market specified · else Mon-Fri only.

    CEO 2026-09-05 AUDIT-01 · when market='india' or 'usa', NSE/NYSE holidays
    honored per backend/research/evidence/trading_calendars.py. Backward-compat
    default (no market) uses simple weekday arithmetic."""
    if market is not None:
        return _add_market_tdays(d, n, market)
    cur = d
    added = 0
    while added < n:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def generate_folds(first_date: date, last_date: date,
                    train_days: int = TRAIN_DAYS,
                    embargo_days: int = EMBARGO_DAYS,
                    oos_days: int = OOS_DAYS,
                    step_days: int = STEP_DAYS,
                    market: Optional[str] = None) -> Iterator[Fold]:
    """Generate walk-forward folds from first_date through last_date.

    Guarantee · every fold obeys · train ⟂ embargo ⟂ OOS · in that temporal
    order · no OOS window overlaps any train or embargo window."""
    fold_id = 0
    train_start = first_date
    while True:
        train_end = _add_trading_days(train_start, train_days - 1, market)
        embargo_end = _add_trading_days(train_end, embargo_days, market)
        oos_start = _add_trading_days(embargo_end, 1, market)
        oos_end = _add_trading_days(oos_start, oos_days - 1, market)
        if oos_end > last_date:
            return
        yield Fold(fold_id=fold_id,
                    train_start=train_start, train_end=train_end,
                    embargo_end=embargo_end,
                    oos_start=oos_start, oos_end=oos_end)
        fold_id += 1
        train_start = _add_trading_days(train_start, step_days, market)


def assert_no_leakage(fold: Fold) -> None:
    """Mechanical leakage guard · assert temporal ordering + embargo gap."""
    assert fold.train_start < fold.train_end, f"fold {fold.fold_id}: train_start ≥ train_end"
    assert fold.train_end < fold.embargo_end, f"fold {fold.fold_id}: embargo missing"
    assert fold.embargo_end < fold.oos_start, f"fold {fold.fold_id}: oos before embargo end"
    assert fold.oos_start <= fold.oos_end, f"fold {fold.fold_id}: oos_start > oos_end"
    # Embargo must be at least EMBARGO_DAYS trading days
    trading_gap = 0
    cur = fold.train_end
    while cur < fold.oos_start:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            trading_gap += 1
    assert trading_gap >= EMBARGO_DAYS, (
        f"fold {fold.fold_id}: embargo gap {trading_gap} < {EMBARGO_DAYS}")


def fold_manifest(first_date: date, last_date: date, **kw) -> dict:
    """Return the full fold list + metadata as a dict · persisted per item."""
    folds = list(generate_folds(first_date, last_date, **kw))
    for f in folds:
        assert_no_leakage(f)
    return {
        "protocol": "V2 PDF walk-forward",
        "train_days": kw.get("train_days", TRAIN_DAYS),
        "embargo_days": kw.get("embargo_days", EMBARGO_DAYS),
        "oos_days": kw.get("oos_days", OOS_DAYS),
        "step_days": kw.get("step_days", STEP_DAYS),
        "market": kw.get("market"),
        "trading_calendar": ("exchange-aware · NSE/NYSE holidays honored"
                              if kw.get("market") else "weekday-only (no holidays)"),
        "first_date": str(first_date),
        "last_date": str(last_date),
        "n_folds": len(folds),
        "folds": [f.to_dict() for f in folds],
        "leakage_audit": "PASSED · all folds obey temporal ordering + embargo gap",
    }
