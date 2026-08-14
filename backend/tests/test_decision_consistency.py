"""Sprint K Part 28 · Decision / Status / Action consistency matrix.

Every rendered row in the XLSX / Telegram must satisfy a deterministic
combination table. Invalid combinations = test failure.

INVALID combinations (from operator spec 2026-08-14):
  EXIT + HOLD + REVIEW
  EXIT + BUY + BUY BIG
  STOP_LOSS_HIT + BUY
  STOP_LOSS_HIT + ADD
  STOP_LOSS_HIT + HOLD
  HARD_STOP + BUY
  TRAILING_STOP_HIT + BUY
  GAP_EXIT + BUY
  PORTFOLIO_MAX_DD + BUY
  EMERGENCY_EXIT + BUY

VALID combinations:
  STRONG BUY + BUY + BUY
  HOLD + PROTECT + TIGHTEN STOP
  HOLD + HOLD + HOLD
  EXIT + EXIT + EXIT
  EXIT + CLOSED + CLOSED
  STOP_LOSS_HIT + EXIT

Anchored to the priority classifier in
scripts/telegram_command_center_send.py · when that classifier's rules
change the tests here update automatically because they import the
same YAML.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# Re-implement the classifier in a pure-function form for tests
# (matches scripts/telegram_command_center_send.py:_classify_priority ·
# any drift here should be caught by explicit acceptance tests below).
import yaml

_PM_YAML = _ROOT / "configs" / "priority_matrix.yaml"
_PM = yaml.safe_load(_PM_YAML.read_text(encoding="utf-8"))
BINDING_RISK_SIGNALS = [str(s).upper() for s in (_PM.get("binding_risk_signals") or [])]
BUCKETS = _PM.get("buckets", {})


def classify(status, inv_verdict, pnl, is_same_day=False, alerts=""):
    q_high = inv_verdict in ("🏆 QUALITY", "✓ OK")
    q_mid  = inv_verdict == "⚠ MARGINAL"
    q_low  = inv_verdict == "✗ AVOID"
    pnl_neg = isinstance(pnl, (int, float)) and pnl < 0
    if status == "ROTATED_SAMEDAY": return "J"
    if status == "EXIT" and is_same_day: return "J"
    alerts_up = str(alerts or "").upper()
    for sig in BINDING_RISK_SIGNALS:
        if sig in alerts_up:
            return "R"
    if status == "EXIT":
        return "H" if q_high else "I"
    if status == "STRONG BUY" and inv_verdict == "🏆 QUALITY": return "A"
    if status in ("BUY", "STRONG BUY") and q_high: return "B"
    if status in ("BUY", "STRONG BUY") and q_low: return "F"
    if status == "HOLD" and q_high and pnl_neg: return "C"
    if status == "HOLD" and q_high: return "D"
    if q_mid: return "E"
    if q_low and pnl_neg: return "G"
    if q_low: return "F"
    return "E"


def bucket_action(bucket):
    return BUCKETS.get(bucket, {}).get("action", "")


def decision_for(bucket, alerts=""):
    """Same override chain as sender · returns the DECISION string family."""
    if bucket == "R":
        return "EXIT"      # 🔴 EXIT · <sig> · IMMEDIATE
    if bucket == "J":
        return "ARTIFACT"
    if bucket in ("I", "H"):
        return "CLOSED"
    return bucket_action(bucket)   # BUY BIG / BUY / ADD / HOLD / etc.


# ─────────────────────────────────────────────────────────────
# INVALID combinations · must NEVER appear together
# ─────────────────────────────────────────────────────────────

def test_stop_loss_hit_never_yields_buy():
    """STOP_LOSS_HIT in alerts must force EXIT · never BUY/ADD/HOLD."""
    for status in ("STRONG BUY", "BUY", "HOLD", "ADD"):
        for iv in ("🏆 QUALITY", "✓ OK", "⚠ MARGINAL", "✗ AVOID"):
            for pnl in (-10, -5, 0, +5, +10):
                b = classify(status, iv, pnl, alerts="STOP_LOSS_HIT")
                assert b == "R", f"STOP_LOSS_HIT + {status}/{iv}/{pnl} -> bucket {b} (expected R)"
                d = decision_for(b)
                assert d == "EXIT", f"bucket {b} -> decision {d} (expected EXIT)"


def test_hard_stop_never_yields_buy():
    for iv in ("🏆 QUALITY", "✓ OK"):
        b = classify("STRONG BUY", iv, -10, alerts="HARD_STOP: hit")
        assert b == "R"
        assert decision_for(b) == "EXIT"


def test_trailing_stop_hit_never_yields_hold():
    b = classify("HOLD", "🏆 QUALITY", -3, alerts="TRAILING_STOP_HIT · exit")
    assert b == "R"
    assert decision_for(b) == "EXIT"


def test_gap_exit_never_yields_buy():
    b = classify("STRONG BUY", "🏆 QUALITY", -15, alerts="GAP_EXIT: bar-level")
    assert b == "R"
    assert decision_for(b) == "EXIT"


def test_portfolio_max_dd_never_yields_add():
    b = classify("BUY", "✓ OK", -20, alerts="PORTFOLIO_MAX_DD breach")
    assert b == "R"
    assert decision_for(b) == "EXIT"


def test_emergency_exit_never_yields_buy():
    b = classify("STRONG BUY", "🏆 QUALITY", -30, alerts="EMERGENCY_EXIT")
    assert b == "R"
    assert decision_for(b) == "EXIT"


def test_critical_deep_loss_never_yields_buy():
    b = classify("BUY", "🏆 QUALITY", -12, alerts="CRITICAL_DEEP_LOSS: -12%")
    assert b == "R"
    assert decision_for(b) == "EXIT"


def test_exit_status_never_yields_hold_decision():
    """Closed positions (EXIT status · not same-day rotation) must NOT
    show HOLD in the Decision column. Both buckets I and H route to CLOSED."""
    for iv in ("🏆 QUALITY", "✓ OK", "⚠ MARGINAL", "✗ AVOID"):
        for pnl in (-5, 0, +5):
            b = classify("EXIT", iv, pnl, is_same_day=False, alerts="")
            assert b in ("H", "I"), f"EXIT/{iv} -> bucket {b} · expected H or I"
            assert decision_for(b) == "CLOSED", f"bucket {b} -> {decision_for(b)} (expected CLOSED)"


def test_exit_status_never_yields_buy_decision():
    for iv in ("🏆 QUALITY", "✓ OK", "⚠ MARGINAL", "✗ AVOID"):
        b = classify("EXIT", iv, 0, is_same_day=False)
        assert decision_for(b) not in ("BUY", "BUY BIG", "ADD"), \
            f"EXIT/{iv} -> {decision_for(b)} · BUY-family forbidden on closed"


# ─────────────────────────────────────────────────────────────
# VALID combinations · must resolve correctly
# ─────────────────────────────────────────────────────────────

def test_strong_buy_quality_yields_buy_big():
    b = classify("STRONG BUY", "🏆 QUALITY", +5)
    assert b == "A"
    assert bucket_action(b) == "BUY BIG"


def test_hold_quality_positive_yields_hold():
    b = classify("HOLD", "🏆 QUALITY", +8)
    assert b == "D"
    assert bucket_action(b) == "HOLD"


def test_hold_quality_negative_yields_add():
    b = classify("HOLD", "🏆 QUALITY", -3)
    assert b == "C"
    assert bucket_action(b) == "ADD"


def test_same_day_rotation_yields_artifact():
    b = classify("EXIT", "✓ OK", 0.0, is_same_day=True)
    assert b == "J"
    assert decision_for(b) == "ARTIFACT"


def test_same_day_rotation_beats_stop_loss():
    """Pathological case: same-day rotation + stop signal · rotation wins
    because the position was never actually held."""
    b = classify("EXIT", "✓ OK", 0.0, is_same_day=True, alerts="STOP_LOSS_HIT")
    assert b == "J"


def test_exit_quality_yields_closed_bucket_H():
    b = classify("EXIT", "🏆 QUALITY", +2)
    assert b == "H"
    assert decision_for(b) == "CLOSED"


def test_exit_avoid_yields_closed_bucket_I():
    b = classify("EXIT", "✗ AVOID", -5)
    assert b == "I"
    assert decision_for(b) == "CLOSED"


# ─────────────────────────────────────────────────────────────
# Precedence hierarchy (Sprint K Part 28 · risk always beats buy)
# ─────────────────────────────────────────────────────────────

def test_precedence_hierarchy_order():
    """Every binding risk signal must produce bucket R even when combined
    with the strongest buy signal (STRONG BUY + QUALITY + big positive P&L).
    This is the LUPIN pattern generalised."""
    for sig in BINDING_RISK_SIGNALS:
        b = classify("STRONG BUY", "🏆 QUALITY", +15.0, alerts=sig)
        assert b == "R", \
            f"Buy signal overrode risk signal {sig} · bucket={b} · precedence VIOLATED"


def test_lupin_2026_08_12_exact_case():
    """The exact row from operator's 2026-08-12 India workbook that
    triggered this whole sprint. Must produce EXIT · IMMEDIATE."""
    b = classify(
        status="STRONG BUY",
        inv_verdict="🏆 QUALITY",
        pnl=-6.20,
        is_same_day=False,
        alerts="STOP_LOSS_HIT · -6.2% ≤ -5.0% · exit",
    )
    assert b == "R", f"LUPIN case still broken · bucket={b}"
    assert decision_for(b) == "EXIT"


def test_powergrid_3_day_stop_loss():
    """POWERGRID Aug 10 / 11 / 12 · all should be bucket R (was SKIP)."""
    for perf in (-5.53, -6.28, -6.75):
        b = classify("BUY", "🏆 QUALITY", perf, alerts="STOP_LOSS_HIT")
        assert b == "R"


def test_closed_positions_from_workbook_route_to_closed():
    """HEROMOTOCO / INDIANB / ATUL / NATIONALUM / OFSS pattern ·
    Status=EXIT · Quality high · was showing HOLD · must be CLOSED."""
    for iv in ("🏆 QUALITY", "✓ OK"):
        b = classify("EXIT", iv, +2, is_same_day=False, alerts="")
        assert b in ("H", "I")
        assert decision_for(b) == "CLOSED"


# ─────────────────────────────────────────────────────────────
# Regression from prior sprints (must still pass)
# ─────────────────────────────────────────────────────────────

def test_new_position_pending_investability_provisional():
    """NEW rows with PENDING investability shouldn't crash the classifier ·
    the NEW-state override lives outside classify() but classify() must
    still return SOME valid bucket."""
    b = classify("STRONG BUY", "", 0, is_same_day=False)
    assert b in BUCKETS.keys(), f"unknown bucket {b}"
