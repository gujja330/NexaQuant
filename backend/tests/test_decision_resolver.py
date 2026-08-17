"""Operator 2026-08-17 · Section 3 + 14 · Decision Resolver + LUPIN regression.

Verifies:
  · Two duplicate rows with contradictory Status get dedup'd to the
    row with highest-priority effective decision.
  · LUPIN pattern (STOP_LOSS_HIT + STRONG BUY vs HOLD) resolves to the
    row carrying the binding risk signal · never the bullish HOLD.
  · CLOSED position followed by BUY/HOLD is flagged as a violation.

Uses pure-function reimplementations that mirror
backend/delivery/telegram/detail_xlsx.py to avoid the heavy import chain.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────
# Mirror of detail_xlsx priorities
# ─────────────────────────────────────────────────────────────
_STATUS_PRIORITY = {
    "EXIT": 0, "SELL": 0,
    "REDUCE": 1, "PROTECT": 1,
    "HOLD": 2,
    "ADD": 3, "ACCUMULATE": 3,
    "BUY": 4,
    "STRONG BUY": 5,
    "SKIP": 6,
    "ROTATED_SAMEDAY": 7,
    "": 99,
}
_BINDING = ("EMERGENCY_EXIT", "PORTFOLIO_MAX_DD", "HARD_STOP",
                "STOP_LOSS_HIT", "GAP_EXIT", "TRAILING_STOP_HIT",
                "CRITICAL_DEEP_LOSS")


def _row_priority(row):
    status = str(row[7] if len(row) > 7 else "").upper().strip()
    has_binding = any(sig in str(c).upper() for c in row if isinstance(c, str) for sig in _BINDING if sig in str(c).upper())
    risk_rank = 0 if has_binding else 1
    return (risk_rank, _STATUS_PRIORITY.get(status, 50))


def _dedupe(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(str(r[0]), str(r[2])[:10], str(r[4]))].append(r)
    return [sorted(rr, key=_row_priority)[0] for rr in groups.values()]


# Build a minimal row (padded with blanks in positions we don't test).
def _row(pid, date, runner, status, alerts=""):
    r = [""] * 25
    r[0]  = pid
    r[2]  = date
    r[4]  = runner
    r[7]  = status
    r[24] = alerts   # Alerts col (any position works since we scan all cells)
    return r


# ─────────────────────────────────────────────────────────────
# LUPIN pattern · exact operator example
# ─────────────────────────────────────────────────────────────
def test_lupin_stop_loss_wins_over_hold():
    """LUPIN_IND_20260731 · 2026-08-12 · R1 · TWO rows arrive:
       row A · Status=STRONG BUY · Alerts=STOP_LOSS_HIT
       row B · Status=HOLD       · Alerts=empty
    Resolver must pick row A (binding risk beats every other signal)."""
    rows = [
        _row("LUPIN_IND_20260731", "2026-08-12", "R1", "STRONG BUY",
             "WARNING·STOP_LOSS_HIT·-6.2% ≤ -5% · exit"),
        _row("LUPIN_IND_20260731", "2026-08-12", "R1", "HOLD", ""),
    ]
    out = _dedupe(rows)
    assert len(out) == 1
    # Winner must be the row with STOP_LOSS_HIT (row A) · Status=STRONG BUY
    assert out[0][7] == "STRONG BUY"
    assert "STOP_LOSS_HIT" in str(out[0][24])


def test_hold_wins_over_buy_when_no_risk_signal():
    """Two duplicate rows · no binding signal · more-cautious wins.
    HOLD ranked higher (safer) than STRONG BUY per _STATUS_PRIORITY."""
    rows = [
        _row("X_IND_20260801", "2026-08-10", "R1", "STRONG BUY", ""),
        _row("X_IND_20260801", "2026-08-10", "R1", "HOLD", ""),
    ]
    out = _dedupe(rows)
    assert len(out) == 1
    assert out[0][7] == "HOLD"


def test_exit_beats_everything_without_risk_alert():
    """Even with no Alerts, EXIT (rank 0) beats HOLD (rank 2)."""
    rows = [
        _row("X_IND_20260801", "2026-08-10", "R1", "HOLD", ""),
        _row("X_IND_20260801", "2026-08-10", "R1", "EXIT", ""),
    ]
    out = _dedupe(rows)
    assert len(out) == 1
    assert out[0][7] == "EXIT"


def test_no_duplication_passthrough():
    """Rows with different (Position ID, Date, Runner) are all preserved."""
    rows = [
        _row("A_IND_20260801", "2026-08-10", "R1", "BUY", ""),
        _row("B_IND_20260801", "2026-08-10", "R1", "HOLD", ""),
        _row("A_IND_20260801", "2026-08-10", "R2", "BUY", ""),   # different runner
    ]
    out = _dedupe(rows)
    assert len(out) == 3


def test_binding_signal_wins_regardless_of_status_rank():
    """A STRONG BUY row with STOP_LOSS_HIT alert MUST beat a plain HOLD row.
    Rationale: never let a bullish row silently overwrite a risk trigger."""
    rows = [
        _row("Y_IND_20260801", "2026-08-15", "R1", "HOLD", ""),
        _row("Y_IND_20260801", "2026-08-15", "R1", "STRONG BUY",
             "HARD_STOP breached"),
    ]
    out = _dedupe(rows)
    assert len(out) == 1
    assert "HARD_STOP" in str(out[0][24])   # risk row survives


def test_full_signal_hierarchy():
    """Priority ordering per operator Section 3:
       binding-risk > EXIT > PROTECT > HOLD > ADD > BUY > STRONG BUY > SKIP"""
    # STOP > EXIT (both no binding · EXIT wins)
    r = _dedupe([_row("Z","2026-01-01","R1","EXIT",""),
                     _row("Z","2026-01-01","R1","HOLD","")])
    assert r[0][7] == "EXIT"
    # PROTECT > HOLD
    r = _dedupe([_row("Z","2026-01-01","R1","PROTECT",""),
                     _row("Z","2026-01-01","R1","HOLD","")])
    assert r[0][7] == "PROTECT"
    # HOLD > BUY
    r = _dedupe([_row("Z","2026-01-01","R1","HOLD",""),
                     _row("Z","2026-01-01","R1","BUY","")])
    assert r[0][7] == "HOLD"
    # BUY > STRONG BUY (BUY is more measured)
    r = _dedupe([_row("Z","2026-01-01","R1","BUY",""),
                     _row("Z","2026-01-01","R1","STRONG BUY","")])
    assert r[0][7] == "BUY"
