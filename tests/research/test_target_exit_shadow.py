"""Target-exit shadow · the inverted-target defect and the governance boundary.

THE DEFECT THESE TESTS LOCK DOWN
--------------------------------
"Target hit" exists only as a display label in the workbook's exit-reason
normalizer. No engine has ever evaluated a target: it fired 0 times in 131
realized exits. Meanwhile the stop trails upward while the target stays frozen
at entry, so on a strong winner the stop overtakes its own target - 4 of 45
India and 10 of 212 USA positions are in that state.

A stop above its own target is incoherent for a long position regardless of
policy, so the repair is unconditional. Acting on the target is NOT, because
the supporting evidence is a RESEARCH SIGNAL at 11 date units against a
20-date floor. The last test is the one that matters: this module must never
claim production authority.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.research.r3_program.target_exit_shadow import (
    TARGET_EXIT_ENABLED, diagnose_inverted, repair_target, shadow_evaluate)

ROOT = Path(__file__).resolve().parents[2]


# 1 · THE GOVERNANCE BOUNDARY ─────────────────────────────────────────
def test_production_authority_is_off_by_default():
    """The mechanism is built; the authority to act is withheld."""
    assert TARGET_EXIT_ENABLED is False


def test_shadow_output_never_claims_production_authority():
    out = shadow_evaluate([], "2026-10-22")
    assert out["production_authority"] is False
    assert out["target_exit_enabled"] is False
    assert out["governance"]["changes_production"] is False
    assert out["governance"]["effective_date_units"] < out["governance"]["oos_floor"]


# 2 · THE INVERSION DIAGNOSIS ─────────────────────────────────────────
def test_detects_stop_above_target():
    pos = [{"ticker": "X", "entry_price": 100, "current_price": 130,
            "target": 110, "stop": 120, "pnl_pct": 30}]
    d = diagnose_inverted(pos)
    assert d["n_inverted_stop_above_target"] == 1
    assert d["n_target_already_passed"] == 1
    assert d["inverted"][0]["gap"] == pytest.approx(10.0)


def test_coherent_position_is_not_flagged():
    pos = [{"ticker": "Y", "entry_price": 100, "current_price": 104,
            "target": 110, "stop": 95, "pnl_pct": 4}]
    d = diagnose_inverted(pos)
    assert d["n_inverted_stop_above_target"] == 0
    assert d["n_target_already_passed"] == 0


def test_missing_target_is_skipped_not_guessed():
    d = diagnose_inverted([{"ticker": "Z", "entry_price": 100,
                            "current_price": 110, "target": None, "stop": 95}])
    assert d["n_inverted_stop_above_target"] == 0
    assert d["n_target_already_passed"] == 0


# 3 · THE REPAIR INVENTS NO PRICE VIEW ────────────────────────────────
def test_repair_restores_the_ordering_stop_below_target():
    r = repair_target(100.0, 110.0, 120.0)
    assert r["repaired"] is True
    assert r["reason"] == "STOP_WAS_ABOVE_TARGET"
    assert r["target"] > r["stop"], "repair must leave stop below target"


def test_repair_preserves_the_original_reward_distance():
    """The repair re-anchors, it does not re-forecast. A 10% reward target
    stays a 10% reward target, measured from the stop instead of entry."""
    r = repair_target(100.0, 110.0, 120.0)
    assert r["preserved_reward_pct"] == pytest.approx(10.0, abs=0.01)
    assert r["target"] == pytest.approx(120.0 * 1.10, rel=1e-6)


def test_repair_leaves_coherent_targets_untouched():
    r = repair_target(100.0, 110.0, 95.0)
    assert r["repaired"] is False
    assert r["reason"] == "ALREADY_COHERENT"
    assert r["target"] == 110.0


def test_repair_refuses_on_missing_fields_rather_than_inventing():
    for args in ((None, 110.0, 95.0), (100.0, None, 95.0), (100.0, 110.0, None)):
        r = repair_target(*args)
        assert r["repaired"] is False
        assert r["reason"] == "INSUFFICIENT_FIELDS"


def test_repair_never_produces_a_target_below_its_stop():
    """Property check across a grid, including degenerate reward distances."""
    for ep in (50.0, 100.0, 3150.0):
        for tg_mult in (0.5, 0.9, 1.0, 1.02, 1.2):
            for st_mult in (1.05, 1.15, 1.5):
                tg, st = ep * tg_mult, ep * st_mult
                r = repair_target(ep, tg, st)
                if r["repaired"]:
                    assert r["target"] > r["stop"]


# 4 · THE SHADOW DECIDES NOTHING ──────────────────────────────────────
def test_shadow_reports_both_rules_side_by_side():
    pos = [{"ticker": "A", "entry_price": 100, "current_price": 105,
            "target": 103, "stop": 95, "pnl_pct": 5.0},
           {"ticker": "B", "entry_price": 100, "current_price": 101,
            "target": 110, "stop": 95, "pnl_pct": 1.0}]
    out = shadow_evaluate(pos, "2026-10-22", threshold_pct=3.0)
    assert out["TAKE_3PC_rule"]["n_would_close"] == 1      # A only
    assert out["TARGET_rule"]["n_would_close"] == 1        # A only
    assert out["TAKE_3PC_rule"]["sum_pnl_locked_pp"] == pytest.approx(5.0)


def test_shadow_threshold_is_explicit_not_hidden():
    out = shadow_evaluate([], "2026-10-22", threshold_pct=7.5)
    assert out["take_profit_threshold_pct"] == 7.5


# 5 · THE SHIPPED ARTIFACT ────────────────────────────────────────────
@pytest.mark.parametrize("market", ["india", "usa"])
def test_shipped_shadow_artifact_is_governed(market):
    p = ROOT / "reports/research/r3" / ("target_exit_shadow_%s.json" % market)
    if not p.exists():
        pytest.skip("shadow not generated in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["production_authority"] is False
    assert d["governance"]["changes_production"] is False
    assert d["governance"]["evidence_tier"] == "RESEARCH SIGNAL"
    # every inverted case must carry a positive gap, or it is not inverted
    for x in d["inverted_diagnosis"]["inverted"]:
        assert x["gap"] > 0
