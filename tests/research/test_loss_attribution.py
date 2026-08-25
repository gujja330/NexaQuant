# tests/research/test_loss_attribution.py
"""AEGIS · executable spec for loss_attribution_v2 + loss_avoidance_guard.

Each rule an executable spec · run local: pytest tests/research/ -v
"""
from __future__ import annotations

from backend.research.loss_attribution_v2 import (
    classify_exit, recommendation_for, LOSS_CATEGORIES,
)
from backend.research.loss_avoidance_guard import assess_loser


# ═════════════════════════════════════════════════════════════════
# classify_exit · 6-category loss classifier
# ═════════════════════════════════════════════════════════════════
class TestExitClassifier:

    def test_positive_pnl_is_winner(self):
        assert classify_exit(
            pnl_pct=3.2, days_held=15, closed_reason="",
            sector_return_over_hold=1.0, entry_quality="OK",
        ) == "WINNER"

    def test_stop_loss_hit_flag_wins(self):
        assert classify_exit(
            pnl_pct=-4.0, days_held=10,
            closed_reason="STOP_LOSS_HIT",
            sector_return_over_hold=-1.0, entry_quality="OK",
        ) == "STOP_LOSS_HIT"

    def test_early_drop_is_macro_shock(self):
        assert classify_exit(
            pnl_pct=-5.0, days_held=3, closed_reason="",
            sector_return_over_hold=-2.0, entry_quality="OK",
        ) == "MACRO_SHOCK"

    def test_long_hold_flat_is_time_stop(self):
        assert classify_exit(
            pnl_pct=-1.0, days_held=60, closed_reason="",
            sector_return_over_hold=None, entry_quality="OK",
        ) == "TIME_STOP"

    def test_sector_dragged_us_down(self):
        assert classify_exit(
            pnl_pct=-6.0, days_held=15, closed_reason="",
            sector_return_over_hold=-7.0, entry_quality="OK",
        ) == "SECTOR_DRAG"

    def test_quality_false_positive(self):
        assert classify_exit(
            pnl_pct=-7.0, days_held=20, closed_reason="",
            sector_return_over_hold=1.0, entry_quality="QUALITY",
        ) == "QUALITY_FALSE_POSITIVE"

    def test_default_is_thesis_failure(self):
        assert classify_exit(
            pnl_pct=-4.0, days_held=25, closed_reason="",
            sector_return_over_hold=0.0, entry_quality="MARGINAL",
        ) == "THESIS_FAILURE"

    def test_all_categories_have_recommendations(self):
        for cat in LOSS_CATEGORIES + ["WINNER"]:
            r = recommendation_for(cat)
            assert isinstance(r, str) and len(r) > 5


# ═════════════════════════════════════════════════════════════════
# assess_loser · forward-looking verdict ladder
# ═════════════════════════════════════════════════════════════════
class TestLoserVerdict:

    def test_stop_breach_exits(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-01",
            days_held=20, entry_price=100.0, current_price=89.0,
            stop_price=90.0, ma20=95.0, ma50=97.0,
            return_5d=-4.0, return_20d=-8.0,
            quality_band="OK", sector="Technology", sector_status="NEUTRAL",
        )
        assert v.verdict == "EXIT"
        assert any("stop" in s.lower() for s in v.signals_fired)

    def test_quality_avoid_exits(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-01",
            days_held=20, entry_price=100.0, current_price=95.0,
            stop_price=90.0, ma20=97.0, ma50=98.0,
            return_5d=-2.0, return_20d=-4.0,
            quality_band="AVOID", sector="—", sector_status="NEUTRAL",
        )
        assert v.verdict == "EXIT"

    def test_below_both_ma_and_sector_laggard_exits(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-01",
            days_held=25, entry_price=100.0, current_price=90.0,
            stop_price=80.0, ma20=92.0, ma50=95.0,
            return_5d=-1.0, return_20d=-8.0,
            quality_band="OK", sector="Healthcare", sector_status="LAGGARD",
        )
        assert v.verdict == "EXIT"

    def test_below_ma20_short_term_bad_tightens_stop(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-01",
            days_held=15, entry_price=100.0, current_price=95.0,
            stop_price=88.0, ma20=97.0, ma50=98.0,
            return_5d=-4.0, return_20d=-2.0,
            quality_band="OK", sector="—", sector_status="NEUTRAL",
        )
        assert v.verdict == "TIGHTEN_STOP"

    def test_marginal_quality_loss_tightens(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-01",
            days_held=25, entry_price=100.0, current_price=93.0,
            stop_price=85.0, ma20=99.0, ma50=100.0,
            return_5d=-1.0, return_20d=-4.0,
            quality_band="MARGINAL", sector="—", sector_status="NEUTRAL",
        )
        assert v.verdict == "TIGHTEN_STOP"

    def test_early_damage_reviews(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-20",
            days_held=5, entry_price=100.0, current_price=95.0,
            stop_price=88.0, ma20=99.0, ma50=100.0,
            return_5d=-2.0, return_20d=-2.0,
            quality_band="OK", sector="—", sector_status="NEUTRAL",
        )
        assert v.verdict == "REVIEW"

    def test_minor_loss_trend_intact_holds(self):
        v = assess_loser(
            ticker="X", market="india", entry_date="2026-08-01",
            days_held=25, entry_price=100.0, current_price=98.0,
            stop_price=88.0, ma20=98.5, ma50=97.0,
            return_5d=0.5, return_20d=1.0,
            quality_band="QUALITY", sector="—", sector_status="LEADER",
        )
        assert v.verdict == "HOLD"

    def test_recommendation_never_empty(self):
        for verdict_case in [
            dict(current_price=89.0, stop_price=90.0),   # EXIT
            dict(current_price=95.0, quality_band="AVOID"),  # EXIT
            dict(current_price=95.0, return_5d=-4.0, ma20=97.0),  # TIGHTEN
            dict(current_price=98.0),  # HOLD
        ]:
            defaults = dict(
                ticker="T", market="india", entry_date="2026-08-01",
                days_held=20, entry_price=100.0, current_price=95.0,
                stop_price=80.0, ma20=99.0, ma50=100.0,
                return_5d=-1.0, return_20d=-2.0,
                quality_band="OK", sector="—", sector_status="NEUTRAL",
            )
            defaults.update(verdict_case)
            v = assess_loser(**defaults)
            assert v.recommendation and len(v.recommendation) > 5
