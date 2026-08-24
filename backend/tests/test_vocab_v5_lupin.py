"""Sprint K Part 28 · Wave 8 · vocab v5.0 collapse LUPIN regression.

The existing test_decision_consistency.py locks the classifier → bucket
routing (STOP_LOSS_HIT + BUY must never yield BUY-family). But those
tests assert against the pre-Wave-1 vocab (BUY/HOLD/EXIT/CLOSED/ARTIFACT).

Under Wave 1 vocab v5.0, the operator sees only NEW/ACTIVE/ACTIVE+/EXIT.
This test verifies the post-classifier vocab-collapse layer routes every
STOP_LOSS_HIT variant to 🔴 EXIT · never to 🟢 ACTIVE / 🟢 ACTIVE+ / 🆕 NEW.

Locks the LUPIN 2026-08-12 scenario under the new vocab.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.tests.test_decision_consistency import (
    classify, decision_for, BINDING_RISK_SIGNALS,
)


def _collapse_v5(status, priority_bucket, is_new_position, decision_text=""):
    """Replay of the vocab-v5.0 collapse block in
    scripts/telegram_command_center_send.py (Wave 1)."""
    _dec_upper = str(decision_text or "").upper()
    _is_exit_family = (
        priority_bucket in ("R", "I", "J", "H")
        or "EXIT" in _dec_upper or "CLOSED" in _dec_upper
        or "ARTIFACT" in _dec_upper or "SKIP" in _dec_upper
    )
    _is_buy_family = (
        status in ("BUY", "STRONG BUY", "ACCUMULATE", "ADD", "BUY BIG")
        or " BUY" in _dec_upper or "ADD" in _dec_upper
    )
    if _is_exit_family:
        return "🔴 EXIT"
    if is_new_position and status != "EXIT":
        return "🆕 NEW"
    if _is_buy_family:
        return "🟢 ACTIVE+"
    return "🟢 ACTIVE"


# ─────────────────────────────────────────────────────────────
# LUPIN 2026-08-12 scenario · vocab v5.0
# Status=STRONG BUY · Alerts contains STOP_LOSS_HIT
# Expected classifier bucket = R  → decision text = 🔴 EXIT
# ─────────────────────────────────────────────────────────────


def test_lupin_v5_stop_loss_forces_exit():
    """LUPIN scenario · every STOP_LOSS_HIT variant collapses to 🔴 EXIT."""
    for status in ("STRONG BUY", "BUY", "HOLD", "ADD"):
        for iv in ("🏆 QUALITY", "✓ OK", "⚠ MARGINAL", "✗ AVOID"):
            for pnl in (-15, -5, 0, +5, +12):
                for is_new in (True, False):
                    b = classify(status, iv, pnl, alerts="STOP_LOSS_HIT")
                    d = _collapse_v5(status, b, is_new, decision_text="EXIT · stop")
                    assert d == "🔴 EXIT", (
                        f"LUPIN {status}/{iv}/pnl={pnl}/new={is_new} → {d} · "
                        f"expected 🔴 EXIT (bucket={b})")


def test_lupin_v5_all_binding_signals_force_exit():
    """Every binding risk signal in the config forces 🔴 EXIT under v5.0."""
    for sig in BINDING_RISK_SIGNALS:
        for status in ("STRONG BUY", "BUY", "HOLD"):
            b = classify(status, "🏆 QUALITY", -10, alerts=sig)
            d = _collapse_v5(status, b, False)
            assert d == "🔴 EXIT", (
                f"{sig} + {status} → {d} · expected 🔴 EXIT")


def test_v5_closed_never_shows_active():
    """EXIT status (closed position) never shows 🟢 ACTIVE / 🟢 ACTIVE+ / 🆕 NEW."""
    for iv in ("🏆 QUALITY", "✓ OK", "⚠ MARGINAL", "✗ AVOID"):
        for pnl in (-10, 0, +10):
            b = classify("EXIT", iv, pnl)
            d = _collapse_v5("EXIT", b, is_new_position=False)
            assert d == "🔴 EXIT", (
                f"closed EXIT/{iv}/{pnl} → {d} · expected 🔴 EXIT")


def test_v5_new_position_wins_over_buy_family():
    """When rec_dt == asof (NEW) the row shows 🆕 NEW even if Status=BUY.
    NEW is a lifecycle state that beats the buy-family override."""
    b = classify("BUY", "🏆 QUALITY", +5)
    d = _collapse_v5("BUY", b, is_new_position=True)
    assert d == "🆕 NEW", f"NEW+BUY → {d} · expected 🆕 NEW"


def test_v5_active_plus_when_held_buy():
    """Held BUY/STRONG BUY position (not new · not exit) → 🟢 ACTIVE+."""
    for status in ("BUY", "STRONG BUY", "ADD"):
        b = classify(status, "🏆 QUALITY", +5)
        d = _collapse_v5(status, b, is_new_position=False)
        assert d == "🟢 ACTIVE+", (
            f"held {status} → {d} · expected 🟢 ACTIVE+")


def test_v5_active_when_held_hold():
    """Held HOLD position → 🟢 ACTIVE (no add-more signal)."""
    b = classify("HOLD", "🏆 QUALITY", +5)
    d = _collapse_v5("HOLD", b, is_new_position=False)
    assert d == "🟢 ACTIVE", f"held HOLD → {d} · expected 🟢 ACTIVE"


def test_v5_same_day_artifact_forces_exit():
    """JIOFIN pattern · same-day NEW→EXIT (bucket J) collapses to 🔴 EXIT."""
    b = classify("EXIT", "🏆 QUALITY", 0, is_same_day=True)
    assert b == "J", f"same-day EXIT → bucket {b} · expected J"
    d = _collapse_v5("EXIT", b, is_new_position=True)
    assert d == "🔴 EXIT", f"JIOFIN → {d} · expected 🔴 EXIT"
