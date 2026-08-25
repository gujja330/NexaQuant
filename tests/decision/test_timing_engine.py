# tests/decision/test_timing_engine.py
"""AEGIS · Sprint M.1 · Timing Engine tests."""
from __future__ import annotations

import pytest


class TestMomentumState:

    def test_confirmed_needs_volume_plus_20d_positive(self):
        from backend.decision.timing_engine import _momentum_state, MOMENTUM_CONFIRMED
        assert _momentum_state("QUICK_RISE", rsi=60,
                               volume_confirmed=True,
                               r5=5, r20=10) == MOMENTUM_CONFIRMED

    def test_developing_without_volume(self):
        from backend.decision.timing_engine import _momentum_state, MOMENTUM_DEVELOPING
        # Volume not confirmed · not chase risk (RSI not extreme)
        assert _momentum_state("QUICK_RISE", rsi=60,
                               volume_confirmed=False,
                               r5=5, r20=10) == MOMENTUM_DEVELOPING

    def test_chase_risk_on_extreme_rsi_weak_volume(self):
        from backend.decision.timing_engine import _momentum_state, CHASE_RISK
        assert _momentum_state("QUICK_RISE", rsi=80,
                               volume_confirmed=False,
                               r5=15, r20=25) == CHASE_RISK

    def test_deteriorating_on_quick_fall(self):
        from backend.decision.timing_engine import _momentum_state, MOMENTUM_DETERIORATING
        assert _momentum_state("QUICK_FALL", rsi=45,
                               volume_confirmed=False,
                               r5=-6, r20=-8) == MOMENTUM_DETERIORATING

    def test_oversold_fall_is_developing(self):
        from backend.decision.timing_engine import _momentum_state, MOMENTUM_DEVELOPING
        # RSI < 30 · potential rebound setup
        assert _momentum_state("QUICK_FALL", rsi=25,
                               volume_confirmed=False,
                               r5=-6, r20=-8) == MOMENTUM_DEVELOPING

    def test_no_signal_when_ignore(self):
        from backend.decision.timing_engine import _momentum_state, NO_SIGNAL
        assert _momentum_state("IGNORE", rsi=None,
                               volume_confirmed=False,
                               r5=None, r20=None) == NO_SIGNAL


class TestEntryQuality:

    def test_good_entry_neutral_rsi(self):
        from backend.decision.timing_engine import _entry_quality
        assert _entry_quality(rsi=55, r5=2, r20=5) == "GOOD"

    def test_extended_on_high_rsi(self):
        from backend.decision.timing_engine import _entry_quality
        assert _entry_quality(rsi=80, r5=2, r20=5) == "EXTENDED"

    def test_extended_on_big_5d_move(self):
        from backend.decision.timing_engine import _entry_quality
        assert _entry_quality(rsi=60, r5=12, r20=15) == "EXTENDED"

    def test_poor_on_falling_knife(self):
        from backend.decision.timing_engine import _entry_quality
        assert _entry_quality(rsi=20, r5=-8, r20=-20) == "POOR"


class TestDecisionMatrix:

    def test_quality_confirmed_good_is_buy(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_CONFIRMED, DECISION_BUY)
        d, r, s, rec = decide(
            investability_band="QUALITY",
            momentum_state=MOMENTUM_CONFIRMED,
            entry_quality="GOOD",
            sector_regime="LEADER", market_regime="BULL",
        )
        assert d == DECISION_BUY
        assert rec == "PRODUCTION_CANDIDATE"

    def test_quality_extended_is_watch(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_CONFIRMED, DECISION_WATCH)
        d, r, s, rec = decide(
            investability_band="QUALITY",
            momentum_state=MOMENTUM_CONFIRMED,
            entry_quality="EXTENDED",
            sector_regime="NEUTRAL", market_regime="BULL",
        )
        assert d == DECISION_WATCH

    def test_quality_developing_is_watch(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_DEVELOPING, DECISION_WATCH)
        d, r, s, rec = decide(
            investability_band="QUALITY",
            momentum_state=MOMENTUM_DEVELOPING,
            entry_quality="GOOD",
            sector_regime="NEUTRAL", market_regime="NEUTRAL",
        )
        assert d == DECISION_WATCH

    def test_low_quality_strong_move_is_chase_risk(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_CONFIRMED, DECISION_CHASE_RISK)
        d, r, s, rec = decide(
            investability_band="AVOID",
            momentum_state=MOMENTUM_CONFIRMED,
            entry_quality="GOOD",
            sector_regime="LEADER", market_regime="BULL",
        )
        assert d == DECISION_CHASE_RISK

    def test_quality_dip_oversold_is_rebound_watch(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_DEVELOPING, DECISION_REBOUND_WATCH)
        # HIGH quality + oversold + developing (rebound setup)
        d, r, s, rec = decide(
            investability_band="QUALITY",
            momentum_state=MOMENTUM_DEVELOPING,
            entry_quality="POOR",   # oversold zone
            sector_regime="NEUTRAL", market_regime="NEUTRAL",
        )
        assert d == DECISION_REBOUND_WATCH

    def test_r1_deteriorating_is_hold_not_exit(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_DETERIORATING, DECISION_HOLD)
        d, r, s, rec = decide(
            investability_band="QUALITY",
            momentum_state=MOMENTUM_DETERIORATING,
            entry_quality="GOOD",
            sector_regime="NEUTRAL", market_regime="NEUTRAL",
            runner="R1",
        )
        assert d == DECISION_HOLD   # R1 · confirmation-only · never exit on momentum alone

    def test_r2_deteriorating_is_protect(self):
        from backend.decision.timing_engine import (
            decide, MOMENTUM_DETERIORATING, DECISION_PROTECT)
        d, r, s, rec = decide(
            investability_band="QUALITY",
            momentum_state=MOMENTUM_DETERIORATING,
            entry_quality="GOOD",
            sector_regime="NEUTRAL", market_regime="NEUTRAL",
            runner="R2",
        )
        assert d == DECISION_PROTECT   # R2 · more responsive


class TestCompute:

    def test_empty_returns_zero(self, tmp_path):
        from backend.decision import timing_engine as _te
        rep = _te.compute(tmp_path, "india")
        assert rep.n_evaluated == 0

    def test_summary_line(self, tmp_path):
        from backend.decision import timing_engine as _te
        rep = _te.compute(tmp_path, "india")
        s = _te.summary_line(rep)
        assert "timing_engine" in s
