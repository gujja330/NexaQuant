# tests/delivery/test_row_classifier.py
"""AEGIS · executable spec for the delivery row classifier.

Each test is a repeat-operator-issue turned into an assertion. If a test
fails, Telegram delivery is BLOCKED by CI (mon001-daily.yml → this suite).

Run local:  pytest tests/delivery/ -v
Run CI:     same · runs before every Telegram send
"""
from __future__ import annotations

import pytest

from backend.delivery.row_classifier import (
    classify_bucket, classify_row,
    is_legit_multi_runner_appearance,
    RowDecision,
    SECTION_ACTION, SECTION_ACTIVE, SECTION_NEW, SECTION_CLOSED,
)


# ═════════════════════════════════════════════════════════════════
# A17 · No EXIT-action row ever lands in the ACTIVE (green) section.
# Historical trigger: BATAINDIA, TATAPOWER kept surfacing in ACTIVE
# despite being flagged EXIT.
# ═════════════════════════════════════════════════════════════════
class TestA17_ExitNeverInActive:

    def test_exit_status_high_quality_goes_to_closed(self):
        d = classify_row(
            ticker="TATAPOWER", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-25",
            asof_iso="2026-08-25",
            status="EXIT", alerts="",
            entry_price=350.0, current_price=300.0,
            stop_price=310.0, t1_price=400.0, pnl_pct=-0.14,
            inv_verdict="🏆 QUALITY",
        )
        assert d.section == SECTION_CLOSED
        assert d.action_str.startswith("🔴 EXIT")
        assert d.verdict == "EXIT"

    def test_exit_status_low_quality_goes_to_closed(self):
        d = classify_row(
            ticker="BATAINDIA", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-25",
            asof_iso="2026-08-25",
            status="EXIT", alerts="",
            entry_price=1500.0, current_price=1200.0,
            stop_price=1300.0, t1_price=1700.0, pnl_pct=-0.20,
            inv_verdict="✗ AVOID",
        )
        assert d.section == SECTION_CLOSED

    def test_hold_neg_pnl_no_quality_boost_goes_to_action(self):
        """The BATAINDIA/TATAPOWER pattern · Status=HOLD but structurally
        broken · must NOT land in ACTIVE."""
        d = classify_row(
            ticker="BATAINDIA", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-20",
            asof_iso="2026-08-25",
            status="HOLD", alerts="",
            entry_price=1500.0, current_price=1200.0,
            stop_price=1300.0, t1_price=1700.0, pnl_pct=-0.20,
            inv_verdict="",  # no quality boost
        )
        assert d.section == SECTION_ACTION, \
            f"HOLD-underwater must go to ACTION, got {d.section}"
        assert d.action_str.startswith("🔴 EXIT")

    def test_binding_risk_goes_to_action(self):
        """Stop-hit today → ACTION REQUIRED, not ACTIVE."""
        d = classify_row(
            ticker="LUPIN", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-15",
            asof_iso="2026-08-25",
            status="HOLD", alerts="STOP_LOSS_HIT triggered",
            entry_price=2000.0, current_price=1900.0,
            stop_price=1900.0, t1_price=2200.0, pnl_pct=-0.05,
            inv_verdict="🏆 QUALITY",
            decision_basis="stop breached",
        )
        assert d.section == SECTION_ACTION
        assert d.bucket == "R"
        assert d.action_str.startswith("🔴 EXIT")

    def test_all_buckets_section_consistent(self):
        """No bucket ever pairs an EXIT action with ACTIVE section."""
        # Cross-product: statuses × alerts × pnl × investability
        for status in ("BUY", "STRONG BUY", "HOLD", "EXIT"):
            for pnl in (-0.10, 0.0, 0.10):
                for iv in ("🏆 QUALITY", "✓ OK", "✗ AVOID", ""):
                    d = classify_row(
                        ticker="TEST", market="india",
                        row_date_iso="2026-08-25",
                        rec_date_iso="2026-08-25",
                        asof_iso="2026-08-25",
                        status=status, alerts="",
                        entry_price=100.0, current_price=100*(1+pnl),
                        stop_price=90.0, t1_price=120.0, pnl_pct=pnl,
                        inv_verdict=iv,
                    )
                    if d.action_str.startswith("🔴 EXIT"):
                        assert d.section in (SECTION_ACTION, SECTION_CLOSED), \
                            (f"A17 · status={status} pnl={pnl} iv={iv!r} · "
                             f"EXIT action but section={d.section}")


# ═════════════════════════════════════════════════════════════════
# A18 · reason text is plain English, no "→ TK.NS · Xpp alpha" jargon.
# ═════════════════════════════════════════════════════════════════
class TestA18_ReasonPlainEnglish:

    @pytest.mark.parametrize("bad_basis", [
        "→ LUPIN.NS · 2pp alpha",
        "Rotation → TATA.NS · Xpp",
        "→ RELIANCE alpha uplift",
    ])
    def test_jargon_stripped_from_reason(self, bad_basis):
        d = classify_row(
            ticker="X", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-25",
            asof_iso="2026-08-25",
            status="EXIT", alerts="",
            entry_price=100.0, current_price=95.0,
            stop_price=90.0, t1_price=120.0, pnl_pct=-0.05,
            inv_verdict="",
            decision_basis=bad_basis,
        )
        for tok in ("→", "Xpp", "xpp"):
            assert tok not in d.reason, \
                f"A18 · jargon '{tok}' leaked into reason={d.reason!r}"

    def test_r_bucket_reason_from_alert(self):
        d = classify_row(
            ticker="X", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-25",
            asof_iso="2026-08-25",
            status="HOLD", alerts="STOP_LOSS_HIT",
            entry_price=100.0, current_price=90.0,
            stop_price=90.0, t1_price=120.0, pnl_pct=-0.10,
            inv_verdict="🏆 QUALITY",
        )
        assert "Stop Loss Hit" in d.reason


# ═════════════════════════════════════════════════════════════════
# A22 / A24 · multi-runner dedup · same ticker can legitimately show
# up in Portfolio (R1 ACTIVE) AND Exit History (R2 CLOSED).
# ═════════════════════════════════════════════════════════════════
class TestA22_A24_MultiRunnerDedup:

    def test_same_runner_in_both_is_bug(self):
        assert is_legit_multi_runner_appearance(
            portfolio_runners={"R1"}, exit_runners={"R1"},
        ) is False

    def test_different_runners_is_legit(self):
        assert is_legit_multi_runner_appearance(
            portfolio_runners={"R1"}, exit_runners={"R2"},
        ) is True

    def test_r2_active_r1_closed_is_legit(self):
        assert is_legit_multi_runner_appearance(
            portfolio_runners={"R2"}, exit_runners={"R1"},
        ) is True

    def test_empty_sets_not_legit(self):
        assert is_legit_multi_runner_appearance(
            portfolio_runners=set(), exit_runners={"R1"},
        ) is False
        assert is_legit_multi_runner_appearance(
            portfolio_runners={"R1"}, exit_runners=set(),
        ) is False


# ═════════════════════════════════════════════════════════════════
# Constructor invariant · RowDecision refuses to exist in an invalid state.
# ═════════════════════════════════════════════════════════════════
class TestRowDecisionInvariants:

    def test_exit_action_in_active_section_raises(self):
        with pytest.raises(ValueError, match="A17"):
            RowDecision(
                section=SECTION_ACTIVE,
                action_str="🔴 EXIT · P&L -5.0% · exit ₹100",
                verdict="EXIT", bucket="G",
                reason="test", sortkey=(2, 0),
            )

    def test_jargon_in_reason_raises(self):
        with pytest.raises(ValueError, match="A18"):
            RowDecision(
                section=SECTION_ACTIVE,
                action_str="🟢 ACTIVE · stop ₹90 · P&L +5.0%",
                verdict="ACTIVE", bucket="D",
                reason="Rotation → LUPIN.NS · 2pp alpha",
                sortkey=(2, 0),
            )

    def test_new_action_only_in_new_or_action_section(self):
        # Trying NEW action in ACTIVE section must raise
        with pytest.raises(ValueError, match="A17"):
            RowDecision(
                section=SECTION_ACTIVE,
                action_str="🟣 NEW · TCS @ ₹3500 · stop ₹3300 · T1 ₹3800",
                verdict="NEW", bucket="E",
                reason="test", sortkey=(1, 0),
            )


# ═════════════════════════════════════════════════════════════════
# Same-day new opp · rec_date == asof and not EXIT → NEW section.
# ═════════════════════════════════════════════════════════════════
class TestSameDayNew:

    def test_e_bucket_rec_today_is_new(self):
        d = classify_row(
            ticker="TCS", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-08-25",
            asof_iso="2026-08-25",
            status="BUY", alerts="",
            entry_price=3500.0, current_price=3500.0,
            stop_price=3300.0, t1_price=3800.0, pnl_pct=0.0,
            inv_verdict="",  # no quality tag · falls to E
        )
        assert d.section == SECTION_NEW
        assert d.action_str.startswith("🟣 NEW")

    def test_old_rec_not_new(self):
        d = classify_row(
            ticker="TCS", market="india",
            row_date_iso="2026-08-25", rec_date_iso="2026-07-15",
            asof_iso="2026-08-25",
            status="BUY", alerts="",
            entry_price=3400.0, current_price=3500.0,
            stop_price=3300.0, t1_price=3800.0, pnl_pct=0.03,
            inv_verdict="",
        )
        assert d.section == SECTION_ACTIVE
