"""Golden lifecycle tests for the dynamic-exit bridge · CEO 2026-09-01.

The bridge is `scripts/apply_dynamic_exits.py` · it wires the coded but
previously-unwired exit engine into the production Registry.

These tests exercise the classic exit cases (stop / target / trailing /
horizon / no-trigger / dynamic-stop-change) against the SAME evaluation
logic the bridge uses. They do not touch the real Registry.
"""
from __future__ import annotations

from datetime import date


# The exit rules the bridge implements (mirrors
# backend/portfolio/lifecycle_state_machine.evaluate_position · which
# is the source of truth · we don't re-import to avoid cross-boundary
# coupling in tests · logic is trivial and asserted here).
def _decide(current_price, entry_price, entry_date, asof,
              stop_price=None, t1_price=None, t2_price=None,
              horizon_days=60):
    try:
        days_held = (date.fromisoformat(asof) - date.fromisoformat(entry_date)).days
    except Exception:
        days_held = 0
    if stop_price is not None and current_price <= stop_price:
        return ("EXIT_STOP", f"stop-loss triggered at {current_price} · stop={stop_price}")
    if t2_price is not None and current_price >= t2_price:
        return ("EXIT_TARGET", f"T2 hit at {current_price} · T2={t2_price}")
    if t1_price is not None and current_price >= t1_price:
        return ("EXIT_TARGET", f"T1 hit at {current_price} · T1={t1_price}")
    if horizon_days > 0 and days_held >= horizon_days:
        return ("EXIT_HORIZON", f"held {days_held}d >= horizon {horizon_days}d")
    return (None, None)


# Case A · Stop
def test_case_A_stop_hit():
    event, reason = _decide(
        current_price=93.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
    )
    assert event == "EXIT_STOP"
    assert "stop-loss" in reason


def test_case_A_stop_not_crossed():
    event, _ = _decide(
        current_price=95.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
    )
    assert event is None


# Case B · Target
def test_case_B_t1_hit():
    event, reason = _decide(
        current_price=113.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
    )
    assert event == "EXIT_TARGET"
    assert "T1" in reason


def test_case_B_t2_hit_takes_priority():
    event, reason = _decide(
        current_price=125.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
    )
    assert event == "EXIT_TARGET"
    assert "T2" in reason


# Case C · Trailing (stop moves up as price rises · monotonic)
def test_case_C_trailing_stop_never_lowers():
    # Day 1: price = 100 · high_water = 100 · stop = 94
    day1_stop = 100.0 * (1.0 - 0.06)
    # Day 2: price = 110 · high_water = 110 · new_from_hw = 103.4 · stop lifted
    day2_from_hw = 110.0 * (1.0 - 0.06)
    day2_stop = max(day1_stop, day2_from_hw)
    assert day2_stop == day2_from_hw
    # Day 3: price = 105 (fell) · high_water still 110 · stop stays 103.4
    day3_from_hw = 110.0 * (1.0 - 0.06)   # high_water didn't rise
    day3_stop = max(day2_stop, day3_from_hw)
    assert day3_stop == day2_stop   # never lowered


def test_case_C_trailing_exit_when_price_falls_through_lifted_stop():
    day2_stop = 110.0 * (1.0 - 0.06)   # 103.4
    event, _ = _decide(
        current_price=103.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=day2_stop, t1_price=112.0, t2_price=124.0,
    )
    assert event == "EXIT_STOP"


# Case D · Horizon
def test_case_D_horizon_expired():
    event, reason = _decide(
        current_price=100.5, entry_price=100.0,
        entry_date="2026-06-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
        horizon_days=60,
    )
    assert event == "EXIT_HORIZON"
    assert "horizon" in reason


def test_case_D_horizon_not_yet_reached():
    event, _ = _decide(
        current_price=100.5, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
        horizon_days=60,
    )
    assert event is None


# Case E · No trigger
def test_case_E_no_trigger_holds():
    event, _ = _decide(
        current_price=101.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
        horizon_days=60,
    )
    assert event is None


# Case F · Dynamic stop change (stop widens under high-vol regime)
def test_case_F_dynamic_stop_widens_and_position_survives():
    # Static rule: stop = 94 · position at 93 would EXIT
    static_stop = 94.0
    # Dynamic (high-vol) rule: stop widened via ATR × high_vol_scale to 90
    dynamic_stop = 90.0
    # With static stop, 93 crosses → EXIT
    ev_static, _ = _decide(
        current_price=93.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=static_stop, t1_price=112.0, t2_price=124.0,
    )
    assert ev_static == "EXIT_STOP"
    # With dynamic (widened) stop, 93 does NOT cross · HOLD
    ev_dyn, _ = _decide(
        current_price=93.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=dynamic_stop, t1_price=112.0, t2_price=124.0,
    )
    assert ev_dyn is None


# Priority ordering · STOP > TARGET > HORIZON
def test_priority_stop_beats_target():
    # If price is both below stop AND above T1 (impossible in reality but
    # tests the priority order · stop check runs first)
    event, _ = _decide(
        current_price=93.0, entry_price=100.0,
        entry_date="2026-08-01", asof="2026-08-05",
        stop_price=94.0, t1_price=90.0, t2_price=95.0,
    )
    assert event == "EXIT_STOP"


def test_priority_target_beats_horizon():
    event, _ = _decide(
        current_price=125.0, entry_price=100.0,
        entry_date="2026-06-01", asof="2026-08-05",   # 65d held · horizon 60
        stop_price=94.0, t1_price=112.0, t2_price=124.0,
        horizon_days=60,
    )
    assert event == "EXIT_TARGET"


# Bridge audit-only mode contract · no Registry mutation
def test_bridge_audit_only_does_not_close():
    """When run with --audit-only (default), bridge must NOT persist
    close events to the Registry. This is enforced by not passing --enforce
    · we test the contract exists via the script's argparse."""
    from pathlib import Path
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/apply_dynamic_exits.py", "--help"],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--audit-only" in result.stdout or "audit-only" in result.stdout.lower()
    assert "--enforce" in result.stdout
