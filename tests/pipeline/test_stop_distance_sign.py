"""A BREACHED position must not block delivery.

CEO 2026-10-27 · USA run #245 blocked with STOP_DISTANCE_MISMATCH while
run #246, three hours later, passed all eight gates on the same book.

The cause was a sign disagreement between producer and checker:

    producer  canonical_daily_lifecycle.py
              dist = (curr - stop) / curr * 100        <- SIGNED

    checker   completeness.stop_distance_invariant
              expected = abs(price - stop) / price*100 <- ABSOLUTE

For a position whose price has gone THROUGH its stop, the producer's
value is legitimately negative - negative is the entire point, it is how
the sheet reports that the stop did not hold. Taking the absolute value
made the two disagree by 2x|dist|: a single breached row produced a
delta of ~10.5pp against a 0.05 tolerance and blocked the whole
delivery.

BREACHED is a legitimate, expected state under the position-lifecycle
lock - advisory, never auto-exited, the VIEW moves to EXIT HISTORY while
the position stays open. So this gate was guaranteed to block delivery
on precisely the days a position went against the book: the days the
operator most needs the sheet.

These tests pin the fix in both directions. The gate must stop flagging
breached rows, and must still catch a displayed distance that is simply
wrong - otherwise the fix would have removed the protection instead of
correcting it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.pipeline.contract.completeness import (
    STOP_DISTANCE_TOLERANCE_PCT, stop_distance_invariant)


def _inv(tmp_path: Path, rows: list) -> dict:
    d = tmp_path / "reports" / "context"
    d.mkdir(parents=True, exist_ok=True)
    (d / "canonical_lifecycle_zz.json").write_text(
        json.dumps({"current": rows}), encoding="utf-8")
    return stop_distance_invariant(tmp_path, "zz")


def _row(ticker, price, stop, shown, state="INTACT"):
    return {"ticker": ticker, "current_price": price, "stop": stop,
            "dist_to_stop_pct": shown, "stop_state": state, "engine": "R2"}


def _producer_dist(curr, stop):
    """Exactly what canonical_daily_lifecycle writes."""
    return round((curr - stop) / curr * 100, 2)


def test_breached_position_does_not_block(tmp_path):
    """Price through the stop · signed negative distance · must PASS."""
    curr, stop = 95.0, 100.0
    shown = _producer_dist(curr, stop)
    assert shown < 0, "a breached row must carry a negative distance"
    inv = _inv(tmp_path, [_row("BRCH", curr, stop, shown, "BREACHED")])
    assert inv["mismatches"] == [], (
        "a breached position was flagged as a stop-distance mismatch. That "
        "is the defect that blocked USA delivery on 2026-10-26 - and it "
        "fires on exactly the days a position goes against the book.")


def test_intact_position_does_not_block(tmp_path):
    curr, stop = 110.0, 100.0
    inv = _inv(tmp_path, [_row("OK", curr, stop, _producer_dist(curr, stop))])
    assert inv["mismatches"] == []


def test_a_genuinely_wrong_distance_is_still_caught(tmp_path):
    """The fix must correct the gate, not disarm it."""
    inv = _inv(tmp_path, [_row("LIE", 110.0, 100.0, 3.00)])
    assert len(inv["mismatches"]) == 1, (
        "a displayed distance that cannot be reconciled with price and stop "
        "must still fail delivery - a stop is the one number on the sheet "
        "someone acts on in a hurry")
    assert inv["mismatches"][0]["ticker"] == "LIE"


def test_breach_and_lie_together(tmp_path):
    """A breached row must not mask a real mismatch beside it."""
    rows = [
        _row("BRCH", 95.0, 100.0, _producer_dist(95.0, 100.0), "BREACHED"),
        _row("FINE", 110.0, 100.0, _producer_dist(110.0, 100.0)),
        _row("LIE", 120.0, 100.0, 1.00),
    ]
    inv = _inv(tmp_path, rows)
    assert [m["ticker"] for m in inv["mismatches"]] == ["LIE"]


@pytest.mark.parametrize("curr,stop", [(95.0, 100.0), (50.0, 99.5),
                                       (1.0, 1.5), (9999.0, 10500.0)])
def test_signed_convention_holds_across_magnitudes(tmp_path, curr, stop):
    inv = _inv(tmp_path, [_row("T", curr, stop, _producer_dist(curr, stop),
                               "BREACHED")])
    assert inv["mismatches"] == [], "breach must pass at any magnitude"


def test_tolerance_is_not_what_was_loosened():
    """The fix was the sign, not the tolerance.

    Widening the tolerance would have hidden real mismatches too - the
    'manufacture readiness by loosening the gate' move. 0.05 exists to
    absorb the producer's 2-decimal rounding and nothing more.
    """
    assert STOP_DISTANCE_TOLERANCE_PCT == 0.05, (
        "the stop-distance tolerance changed. If that was deliberate, say "
        "why here. If it was done to make a block go away, revert it - the "
        "2026-10-27 fix was to the SIGN.")


def test_certification_renders_the_blocking_row():
    """A gate that blocks must say what blocked it.

    Run #245's FIELDS_COMPLETE section rendered identically to the run
    that passed - same rows, same gaps, same sector counts - while the
    offending ticker sat on c.detail unprinted. Once a later run
    overwrote the file the cause was unrecoverable.
    """
    src = (Path(__file__).resolve().parents[2]
           / "backend/pipeline/contract/certification.py").read_text(
        encoding="utf-8")
    assert 'c.detail.get("stop_distance")' in src, (
        "the certification no longer renders stop-distance detail, so a "
        "STOP_DISTANCE_MISMATCH block would again be undiagnosable")
    assert "stop MISMATCH" in src
