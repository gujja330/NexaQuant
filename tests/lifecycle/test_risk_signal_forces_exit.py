"""AEGIS · Regression for stop_loss_not_exit lifecycle inconsistency.

Before fix: a row with a BINDING_RISK_SIGNAL in Alerts kept its bullish
Status (BUY / STRONG BUY / HOLD) — validator surfaced this as
`stop_loss_not_exit` violations (POWERGRID, ITC, SUNPHARMA on
2026-08-26). The lifecycle then contradicted the risk verdict.

Fix at source: `_validate_no_lifecycle_violations` now MUTATES Status
to "EXIT" when a binding risk signal is found, not just log-and-move-on.
This test locks the behavior · a synthetic row with a risk signal
enters as "BUY" and exits the function as "EXIT".
"""
from __future__ import annotations
import pytest


def test_risk_signal_forces_status_exit():
    from backend.delivery.telegram.detail_xlsx import _validate_no_lifecycle_violations
    # Build a minimal row matching the sender's row schema · index 7 = Status,
    # any string cell may contain the alert. Padding with empty strings.
    row = ["PID_TCS_R1_20260101", "", "2026-08-26", "INDIA", "R1",
           "TCS", "TATA CONSULTANCY", "BUY", "", "",
           "STOP_LOSS_HIT · alert"]           # Alerts-like cell
    rows = [row]
    out, n_viol = _validate_no_lifecycle_violations(rows)
    assert n_viol == 1, "Violation should be counted"
    assert out[0][7] == "EXIT", \
        f"Status must be forced to EXIT · got {out[0][7]!r}"


def test_no_risk_signal_leaves_status_untouched():
    from backend.delivery.telegram.detail_xlsx import _validate_no_lifecycle_violations
    row = ["PID_TCS_R1_20260101", "", "2026-08-26", "INDIA", "R1",
           "TCS", "TATA CONSULTANCY", "BUY", "", "",
           "no risk signal here"]
    rows = [row]
    out, n_viol = _validate_no_lifecycle_violations(rows)
    assert n_viol == 0
    assert out[0][7] == "BUY"


def test_exit_status_already_correct_no_mutation():
    """Row already EXIT with risk signal should not double-count violation."""
    from backend.delivery.telegram.detail_xlsx import _validate_no_lifecycle_violations
    row = ["PID_TCS_R1_20260101", "", "2026-08-26", "INDIA", "R1",
           "TCS", "TATA CONSULTANCY", "EXIT", "", "",
           "STOP_LOSS_HIT"]
    rows = [row]
    out, n_viol = _validate_no_lifecycle_violations(rows)
    assert n_viol == 0
    assert out[0][7] == "EXIT"


def test_all_binding_signals_force_exit():
    """Every BINDING_RISK_SIGNALS entry must trigger EXIT mutation."""
    from backend.delivery.telegram.detail_xlsx import (
        _validate_no_lifecycle_violations, _BINDING_RISK_SIGNALS,
    )
    for signal in _BINDING_RISK_SIGNALS:
        row = ["PID", "", "2026-08-26", "INDIA", "R1",
               "TCS", "TCS", "HOLD", "", "", signal]
        rows = [row]
        out, n_viol = _validate_no_lifecycle_violations(rows)
        assert out[0][7] == "EXIT", \
            f"{signal} must force EXIT · got {out[0][7]!r}"
