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
    """Exactly what canonical_daily_lifecycle writes.

    CEO 2026-10-30 · the price is rounded to 2dp FIRST, because that is the
    value the producer persists as `current_price` and the gate recomputes
    from. See test_low_priced_row_reconciles below.
    """
    curr_shown = round(float(curr), 2)
    return round((curr_shown - stop) / curr_shown * 100, 2)


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


# ── boundary and invalid-input cases (CEO 2026-10-27, Phase 4) ───────
#
# The sign fix was verified on clearly-breached and clearly-intact rows.
# These pin the edges, where a sign convention is easiest to get wrong,
# and the malformed inputs that must be classified rather than silently
# passed. They assert the INTENDED contract - signed distance, routed by
# field validity - not merely whatever the code currently returns.

def test_stop_exactly_at_price_is_zero_distance_and_passes(tmp_path):
    """The exact boundary · distance is 0, neither breached nor intact."""
    inv = _inv(tmp_path, [_row("ATPRICE", 100.0, 100.0, 0.0)])
    assert inv["mismatches"] == [], (
        "a stop exactly at price has a distance of exactly 0.0 and must "
        "reconcile · it is the boundary the sign convention pivots on")
    assert inv["rows_with_stop"] == 1


def test_one_tick_either_side_of_the_boundary(tmp_path):
    """Just-breached and just-intact must both reconcile."""
    rows = [
        _row("JUSTBRCH", 99.99, 100.0, _producer_dist(99.99, 100.0),
             "BREACHED"),
        _row("JUSTOK", 100.01, 100.0, _producer_dist(100.01, 100.0)),
    ]
    inv = _inv(tmp_path, rows)
    assert inv["mismatches"] == [], (
        "a one-tick breach must not be flagged · got %s"
        % [m["ticker"] for m in inv["mismatches"]])


def test_zero_price_is_malformed_not_a_mismatch(tmp_path):
    """A zero price cannot divide · it must be classified, not flagged."""
    inv = _inv(tmp_path, [_row("ZEROPX", 0.0, 100.0, -5.0)])
    assert inv["mismatches"] == [], (
        "a zero price was reported as a stop-distance mismatch · it is a "
        "malformed row and must be routed there, not blamed on the sign")
    assert len(inv["malformed_stops"]) == 1
    assert inv["rows_with_stop"] == 0


def test_negative_price_is_malformed(tmp_path):
    inv = _inv(tmp_path, [_row("NEGPX", -10.0, 100.0, -5.0)])
    assert inv["mismatches"] == []
    assert len(inv["malformed_stops"]) == 1


def test_zero_or_negative_stop_is_malformed(tmp_path):
    inv = _inv(tmp_path, [_row("ZEROSTOP", 100.0, 0.0, 100.0),
                          _row("NEGSTOP", 100.0, -5.0, 105.0)])
    assert inv["mismatches"] == []
    assert len(inv["malformed_stops"]) == 2


def test_missing_stop_is_counted_separately(tmp_path):
    """No stop is not a wrong stop."""
    inv = _inv(tmp_path, [{"ticker": "NOSTOP", "current_price": 100.0,
                           "stop": None, "dist_to_stop_pct": None,
                           "stop_state": "NO STOP", "engine": "R2"}])
    assert inv["mismatches"] == []
    assert inv["missing_stops"] == ["NOSTOP"]
    assert inv["rows_with_stop"] == 0


def test_non_numeric_stop_is_not_treated_as_a_number(tmp_path):
    inv = _inv(tmp_path, [{"ticker": "BADSTOP", "current_price": 100.0,
                           "stop": "n/a", "dist_to_stop_pct": 5.0,
                           "stop_state": "INTACT", "engine": "R2"}])
    assert inv["mismatches"] == []
    assert inv["missing_stops"] == ["BADSTOP"]


def test_absent_displayed_distance_is_not_a_mismatch(tmp_path):
    """Nothing displayed cannot contradict the arithmetic."""
    inv = _inv(tmp_path, [{"ticker": "NODIST", "current_price": 110.0,
                           "stop": 100.0, "dist_to_stop_pct": None,
                           "stop_state": "INTACT", "engine": "R2"}])
    assert inv["mismatches"] == []
    assert inv["rows_with_stop"] == 1


def test_a_sign_flipped_display_is_caught_on_an_intact_row(tmp_path):
    """The converse of the fixed bug · the gate must still have teeth.

    An INTACT row whose displayed distance carries the wrong sign is a
    real contradiction and must fail, otherwise the fix would have
    disarmed the gate instead of correcting it.
    """
    inv = _inv(tmp_path, [_row("FLIPPED", 110.0, 100.0, -9.09)])
    assert len(inv["mismatches"]) == 1, (
        "an intact row displaying a negative distance contradicts price and "
        "stop and must fail delivery")
    assert inv["mismatches"][0]["ticker"] == "FLIPPED"


# ── CEO 2026-10-30 · ROUNDING INCOHERENCE ───────────────────────────────
# The sign bug above had a twin. The producer computed dist from the
# full-precision price but persisted `current_price` rounded to 2dp, and
# the gate recomputes from the persisted value. The gap is the half-cent
# the rounding discarded, which moves the distance by
# stop/price^2 * 100 * 0.005 pp - invisible above ~$8.80, not below.
#
# USA ADT blocked three consecutive early runs (10-26, 10-27, 10-28). Each
# time the later run certified only because ADT had left CURRENT, so the
# verdict history read as a schedule problem when it was arithmetic.

ADT_FULL_PRICE = 7.4254     # what the producer computed from
ADT_SHOWN_PRICE = 7.43      # what it persisted · round(7.4254, 2)
ADT_STOP = 6.5507


def test_low_priced_row_reconciles(tmp_path):
    """The exact ADT row that blocked USA three days running."""
    shown = _producer_dist(ADT_FULL_PRICE, ADT_STOP)
    inv = _inv(tmp_path, [_row("ADT", ADT_SHOWN_PRICE, ADT_STOP, shown)])
    assert inv["mismatches"] == [], (
        "ADT · price %.2f · stop %.4f · shown %.2f still cannot reconcile. "
        "This is the row that blocked USA delivery on 2026-10-26, -27 and "
        "-28." % (ADT_SHOWN_PRICE, ADT_STOP, shown))


def test_the_old_formula_would_have_failed_this_row(tmp_path):
    """Pins the defect itself · without it the test above proves nothing."""
    legacy = round((ADT_FULL_PRICE - ADT_STOP) / ADT_FULL_PRICE * 100, 2)
    assert legacy == 11.78
    expected = (ADT_SHOWN_PRICE - ADT_STOP) / ADT_SHOWN_PRICE * 100
    assert abs(expected - legacy) > STOP_DISTANCE_TOLERANCE_PCT, (
        "the pre-fix pairing is no longer out of tolerance, so this "
        "regression test has stopped exercising the bug it was written for")
    inv = _inv(tmp_path, [_row("ADT", ADT_SHOWN_PRICE, ADT_STOP, legacy)])
    assert len(inv["mismatches"]) == 1


@pytest.mark.parametrize("price", [2.07, 3.335, 4.995, 6.125, 7.4254,
                                   8.795, 9.001, 12.345, 47.678, 503.219])
def test_producer_and_gate_agree_at_every_price(tmp_path, price):
    """Coherence must not depend on how expensive the stock is.

    A tolerance that only holds above a price is not a tolerance, it is a
    coin flip weighted by the book.
    """
    stop = round(price * 0.88, 4)
    shown = _producer_dist(price, stop)
    inv = _inv(tmp_path, [_row("SWEEP", round(price, 2), stop, shown)])
    assert inv["mismatches"] == [], (
        "price %s · stop %s · shown %s does not reconcile against the "
        "persisted 2dp price" % (price, stop, shown))
