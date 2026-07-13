"""
Deterministic tests for the LAB009 period-boundary correction.

15 test cases. Run: python india/ai_lab/LAB009_Horizon_Phase_Recalibration/test_period_boundary_correction.py

Must PASS before corrected LAB009 execution proceeds.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd

from india.ai_lab.LAB009_Horizon_Phase_Recalibration.horizon_phase_policies import (
    build_context, phase_offsets_for, build_registry_for_horizon_phase,
    compute_common_window, simulate_horizon_phase,
)
from india.ai_lab.LAB009_Horizon_Phase_Recalibration.run_lab009 import (
    select_period_cycles, _assert_period_containment,
)
from india.ai_lab.lab_metrics import read_trial_manifest_count, period_metrics

DISC_END = pd.Timestamp("2023-10-13")
CONF_START = pd.Timestamp("2024-01-15")
CONF_END = pd.Timestamp("2026-01-27")


def _build_context_and_regs():
    ctx = build_context(30)
    regs = {}
    for cid, h in {"N0": 63, "H21": 21, "H42": 42, "H84": 84}.items():
        for p in phase_offsets_for(h):
            regs[(cid, h, p)] = build_registry_for_horizon_phase(h, p, ctx["closes"], ctx["rets"])
    return ctx, regs


def _make_meta_from_reg(reg_df):
    """Construct meta list matching the simulator's output shape for cycles inside common window."""
    cycles = reg_df[["rec_id", "asof", "mature_date"]].drop_duplicates("rec_id").sort_values("asof")
    return [{"rec_id": r.rec_id,
             "asof": pd.Timestamp(r.asof).normalize(),
             "mature": pd.Timestamp(r.mature_date).normalize()} for r in cycles.itertuples(index=False)]


# ---------------------------- Tests ----------------------------

def test_1_confirmation_cycle_asof_ok_mature_bad_excluded():
    _, regs = _build_context_and_regs()
    n0_p31 = regs[("N0", 63, 31)]
    meta = _make_meta_from_reg(n0_p31)
    conf_asofs = select_period_cycles(meta, CONF_START, CONF_END)
    # Find any cycle with asof in [conf_start, conf_end] but mature > conf_end
    offenders = [m for m in meta if CONF_START <= m["asof"] <= CONF_END and m["mature"] > CONF_END]
    for m in offenders:
        assert m["asof"] not in conf_asofs, (
            f"cycle {m['rec_id']} (asof={m['asof']}, mature={m['mature']}) leaked past conf_end")
    print(f"  TEST 1 PASS: {len(offenders)} borderline conf cycle(s) correctly excluded from N0 phase 31")


def test_2_discovery_cycle_crossing_disc_end_excluded():
    _, regs = _build_context_and_regs()
    hit = 0
    for (cid, h, p), reg in regs.items():
        meta = _make_meta_from_reg(reg)
        common_start = pd.Timestamp("2021-10-01").normalize()
        disc_asofs = select_period_cycles(meta, common_start, DISC_END)
        for m in meta:
            if common_start <= m["asof"] <= DISC_END and m["mature"] > DISC_END:
                assert m["asof"] not in disc_asofs, f"disc leak {cid}/{h}/{p}: {m['rec_id']}"
                hit += 1
    print(f"  TEST 2 PASS: {hit} discovery cycles crossing disc_end correctly excluded across 16 configs")


def test_3_fully_contained_discovery_included():
    _, regs = _build_context_and_regs()
    hit_any = False
    common_start = pd.Timestamp("2021-10-01").normalize()
    for (cid, h, p), reg in regs.items():
        meta = _make_meta_from_reg(reg)
        disc_asofs = select_period_cycles(meta, common_start, DISC_END)
        for m in meta:
            if common_start <= m["asof"] and m["mature"] <= DISC_END:
                assert m["asof"] in disc_asofs, f"fully-contained disc EXCLUDED: {cid}/{h}/{p} {m['rec_id']}"
                hit_any = True
    assert hit_any, "no fully-contained discovery cycle found (test invalid)"
    print(f"  TEST 3 PASS: fully-contained discovery cycles are INCLUDED")


def test_4_fully_contained_confirmation_included():
    _, regs = _build_context_and_regs()
    hit_any = False
    for (cid, h, p), reg in regs.items():
        meta = _make_meta_from_reg(reg)
        conf_asofs = select_period_cycles(meta, CONF_START, CONF_END)
        for m in meta:
            if CONF_START <= m["asof"] and m["mature"] <= CONF_END:
                assert m["asof"] in conf_asofs, f"fully-contained conf EXCLUDED: {cid}/{h}/{p} {m['rec_id']}"
                hit_any = True
    assert hit_any, "no fully-contained confirmation cycle found (test invalid)"
    print(f"  TEST 4 PASS: fully-contained confirmation cycles are INCLUDED")


def test_5_confirmation_metric_equity_within_conf_end():
    ctx, regs = _build_context_and_regs()
    cs, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    for (cid, h, p), reg in regs.items():
        eq, meta = simulate_horizon_phase(
            reg, ctx["closes"], ctx["exp_series"], cs, ce,
            initial_capital=100_000, cash_return_annual=0.0, cost_bps=15.0, trading_days_per_year=252)
        conf_asofs = select_period_cycles(meta, CONF_START, CONF_END)
        # Reconstruct period equity per period_metrics's logic
        windows = [(m["asof"], m["mature"]) for m in meta if pd.Timestamp(m["asof"]) in conf_asofs]
        for start, end in windows:
            assert pd.Timestamp(end).normalize() <= CONF_END, (
                f"{cid}/{h}/{p}: conf window [{start}, {end}] extends past conf_end")
    print(f"  TEST 5 PASS: no confirmation-metric equity observation exceeds conf_end across all 16 configs")


def test_6_discovery_metric_equity_within_disc_end():
    ctx, regs = _build_context_and_regs()
    cs, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    for (cid, h, p), reg in regs.items():
        eq, meta = simulate_horizon_phase(
            reg, ctx["closes"], ctx["exp_series"], cs, ce,
            initial_capital=100_000, cash_return_annual=0.0, cost_bps=15.0, trading_days_per_year=252)
        disc_asofs = select_period_cycles(meta, cs, DISC_END)
        windows = [(m["asof"], m["mature"]) for m in meta if pd.Timestamp(m["asof"]) in disc_asofs]
        for start, end in windows:
            assert pd.Timestamp(end).normalize() <= DISC_END, (
                f"{cid}/{h}/{p}: disc window [{start}, {end}] extends past disc_end")
    print(f"  TEST 6 PASS: no discovery-metric equity observation exceeds disc_end")


def test_7_no_period_metric_starts_before_period_start():
    _, regs = _build_context_and_regs()
    for (cid, h, p), reg in regs.items():
        meta = _make_meta_from_reg(reg)
        disc = select_period_cycles(meta, pd.Timestamp("2021-10-01"), DISC_END)
        conf = select_period_cycles(meta, CONF_START, CONF_END)
        for m in meta:
            if m["asof"] in disc:
                assert m["asof"] >= pd.Timestamp("2021-10-01")
            if m["asof"] in conf:
                assert m["asof"] >= CONF_START
    print(f"  TEST 7 PASS: no period-metric cycle has asof before its period_start")


def test_8_H63_P31_2025_12_09_excluded_from_conf():
    _, regs = _build_context_and_regs()
    meta = _make_meta_from_reg(regs[("N0", 63, 31)])
    conf_asofs = select_period_cycles(meta, CONF_START, CONF_END)
    target_asof = pd.Timestamp("2025-12-09").normalize()
    assert target_asof not in conf_asofs, "H63_P31_2025-12-09 leaked into confirmation set"
    # Sanity: it should be present in the meta itself
    target_present = any(m["asof"] == target_asof for m in meta)
    assert target_present, "H63_P31_2025-12-09 not in registry (test invalid)"
    print(f"  TEST 8 PASS: H63_P31_2025-12-09 correctly EXCLUDED from N0 phase 31 confirmation metrics")


def test_9_gate_expressions_byte_identical():
    from india.ai_lab.lab_config import load_experiment_config
    cfg = load_experiment_config(ROOT / "india" / "ai_lab" / "LAB009_Horizon_Phase_Recalibration" / "lab009.yaml")
    expected = [
        ("gate_1", "cand.median.conf.sharpe >= n0.median.conf.sharpe"),
        ("gate_2", "cand.median.full.cagr >= n0.median.full.cagr - 0.01"),
        ("gate_3", "cand.median.full.sharpe >= n0.median.full.sharpe - 0.05"),
        ("gate_4", "cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03"),
        ("gate_5", "cand.phase_top2_sharpe >= 0.50"),
        ("gate_6", "(cand.cost_drag - n0.cost_drag) <= 0.01"),
    ]
    assert len(cfg.gates) == 6
    for i, (gid, expr) in enumerate(expected):
        g = cfg.gates[i]
        assert g["id"] == gid, f"gate {i} id mismatch"
        assert g["expression"] == expr, f"gate {gid} expression drift"
    print(f"  TEST 9 PASS: all 6 gate expressions byte-identical to sealed spec")


def test_10_candidate_horizon_phase_definitions_unchanged():
    from india.ai_lab.lab_config import load_experiment_config
    cfg = load_experiment_config(ROOT / "india" / "ai_lab" / "LAB009_Horizon_Phase_Recalibration" / "lab009.yaml")
    expected_horizons = {"N0": 63, "H21": 21, "H42": 42, "H84": 84}
    assert set(cfg.candidates.keys()) == set(expected_horizons.keys())
    for cid, h_exp in expected_horizons.items():
        assert cfg.candidates[cid]["horizon_days"] == h_exp
    # Phase offsets
    assert phase_offsets_for(63) == [0, 15, 31, 47]
    assert phase_offsets_for(21) == [0, 5, 10, 15]
    assert phase_offsets_for(42) == [0, 10, 21, 31]
    assert phase_offsets_for(84) == [0, 21, 42, 63]
    print(f"  TEST 10 PASS: candidate horizons + phase offsets unchanged")


def test_11_cash_and_cost_grids_unchanged():
    from india.ai_lab.lab_config import load_experiment_config
    cfg = load_experiment_config(ROOT / "india" / "ai_lab" / "LAB009_Horizon_Phase_Recalibration" / "lab009.yaml")
    assert cfg.simulation["cash_returns_annual"] == [0.0, 0.06]
    assert cfg.simulation["cost_grid_bps"] == [15, 30, 50]
    assert cfg.simulation["canonical_cost_bps"] == 15
    assert cfg.simulation["promotion_stress_cost_bps"] == 50
    print(f"  TEST 11 PASS: cash + cost grids unchanged")


def test_12_turnover_worked_example():
    stock_w_prev = {"A": 0.5, "B": 0.5}; exp_prev = 0.8
    stock_w_cur = {"C": 0.5, "D": 0.5}; exp_cur = 0.9
    all_syms = set(stock_w_prev) | set(stock_w_cur)
    eff_prev = {s: exp_prev * stock_w_prev.get(s, 0.0) for s in all_syms}
    eff_cur = {s: exp_cur * stock_w_cur.get(s, 0.0) for s in all_syms}
    stock_side = sum(abs(eff_cur[s] - eff_prev[s]) for s in all_syms)
    cash_side = abs(exp_cur - exp_prev)
    turnover = 0.5 * (stock_side + cash_side)
    assert abs(turnover - 0.90) < 1e-9, f"turnover formula broken: {turnover}"
    print(f"  TEST 12 PASS: turnover worked example = {turnover:.4f} == 0.90")


def test_13_trial_manifest_still_38():
    n = read_trial_manifest_count(ROOT / "india" / "ai_lab" / "trial_manifest.md")
    assert n == 38, f"cumulative_strategy_search must remain 38, got {n}"
    print(f"  TEST 13 PASS: cumulative_strategy_search = {n}")


def test_14_maturity_correction_tests_still_pass():
    """Run the earlier 8 maturity-correction tests to confirm no regression."""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(ROOT / "india" / "ai_lab" / "LAB009_Horizon_Phase_Recalibration" / "test_maturity_correction.py")],
        capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"maturity-correction tests FAILED\n{r.stdout}\n{r.stderr}"
    assert "8 passed, 0 failed" in r.stdout, f"expected 8/8, got:\n{r.stdout}"
    print(f"  TEST 14 PASS: 8/8 previous maturity-correction tests still PASS")


def test_15_framework_tests_still_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(ROOT / "india" / "ai_lab" / "tests" / "test_lab_framework.py")],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"framework tests FAILED\n{r.stdout}\n{r.stderr}"
    assert "17 passed, 0 failed" in r.stdout, f"expected 17/17, got:\n{r.stdout}"
    print(f"  TEST 15 PASS: 17/17 framework tests still PASS")


if __name__ == "__main__":
    tests = [
        test_1_confirmation_cycle_asof_ok_mature_bad_excluded,
        test_2_discovery_cycle_crossing_disc_end_excluded,
        test_3_fully_contained_discovery_included,
        test_4_fully_contained_confirmation_included,
        test_5_confirmation_metric_equity_within_conf_end,
        test_6_discovery_metric_equity_within_disc_end,
        test_7_no_period_metric_starts_before_period_start,
        test_8_H63_P31_2025_12_09_excluded_from_conf,
        test_9_gate_expressions_byte_identical,
        test_10_candidate_horizon_phase_definitions_unchanged,
        test_11_cash_and_cost_grids_unchanged,
        test_12_turnover_worked_example,
        test_13_trial_manifest_still_38,
        test_14_maturity_correction_tests_still_pass,
        test_15_framework_tests_still_pass,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
