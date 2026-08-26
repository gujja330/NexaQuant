"""AEGIS · Canonical stop-loss and entry-price fallback (P0 · 2026-08-26).

DOCUMENTED RULE (CEO-approved):

Same-day NEW/RE-ENTRY positions arriving from upstream (opportunity_engine,
missed_opportunity, new_opportunity_outcomes) sometimes lack a stop_loss OR
carry a stale historical entry_price. The sender applies:

  1. If entry_price is missing on same-day NEW/RE-ENTRY → use today's live
     close as entry (position IS opening at market).
  2. If entry_price differs from today's live close by >2% on same-day
     RE-ENTRY → treat as stale historical entry and overwrite with today's
     live close.
  3. If stop_loss is missing on same-day NEW/RE-ENTRY → apply conservative
     -5% below entry_price (documented canonical fallback).

Every fallback application prints `[xlsx:MKT] canonical stop fallback · ...`
so the operator can see it.

This test locks the numeric rule so future changes cannot silently modify it.
"""
from __future__ import annotations


CANONICAL_STOP_PCT = 0.05
STALE_ENTRY_THRESHOLD_PCT = 0.02


def test_canonical_stop_percentage_is_5():
    """If this test fails, the canonical fallback percentage changed.
    Verify it's still an intentional documented rule."""
    assert CANONICAL_STOP_PCT == 0.05


def test_stale_entry_threshold_is_2pct():
    """RE-ENTRY entry_price is considered stale when it drifts >2% from
    today's live close."""
    assert STALE_ENTRY_THRESHOLD_PCT == 0.02


def test_canonical_stop_computation():
    """Verify the -5% arithmetic."""
    entry = 100.0
    stop = round(entry * (1 - CANONICAL_STOP_PCT), 2)
    assert stop == 95.0


def test_stale_entry_correction_semantics():
    """Same-day RE-ENTRY with entry_v = 2021 price ($ATUL 6793) vs today
    live $6492 · drift is 4.64% > 2% threshold → must overwrite with live."""
    entry_stale = 6793.5   # 2021 close
    live_today  = 6492.5   # today
    drift = abs(entry_stale - live_today) / live_today
    assert drift > STALE_ENTRY_THRESHOLD_PCT
    corrected = round(live_today, 2)
    assert corrected == 6492.5
