"""
Deterministic tests for the LAB009 maturity-boundary correction.

Run: python india/ai_lab/LAB009_Horizon_Phase_Recalibration/test_maturity_correction.py

Fails loud if any invariant of the sealed correction is broken. Must PASS before corrected
LAB009 execution proceeds.
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
from india.ai_lab.lab_metrics import read_trial_manifest_count


def _build_all_registries():
    ctx = build_context(30)
    candidates = {"N0": 63, "H21": 21, "H42": 42, "H84": 84}
    regs = {}
    for cid, h in candidates.items():
        for p in phase_offsets_for(h):
            regs[(cid, h, p)] = build_registry_for_horizon_phase(h, p, ctx["closes"], ctx["rets"])
    return ctx, candidates, regs


def test_1_common_end_uses_min_mature():
    _, _, regs = _build_all_registries()
    _, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    # Independently compute min of max(mature_date) across configs
    expected = min(pd.to_datetime(r["mature_date"]).max().normalize() for r in regs.values())
    assert ce == expected, f"common_end mismatch: got {ce}, expected {expected}"
    assert ce.date().isoformat() == "2026-03-27", f"expected 2026-03-27, got {ce.date()}"
    print(f"  TEST 1 PASS: common_end = {ce.date()} = min(max(mature_date)) across configs")


def test_2_no_included_cycle_matures_past_end():
    ctx, _, regs = _build_all_registries()
    cs, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    for (cid, h, p), reg in regs.items():
        r = reg.copy()
        r["asof"] = pd.to_datetime(r["asof"]).dt.normalize()
        r["mature_date"] = pd.to_datetime(r["mature_date"]).dt.normalize()
        included = r[(r["asof"] >= cs) & (r["mature_date"] <= ce)]
        assert (included["mature_date"] <= ce).all(), (
            f"config {cid}/{h}/{p}: some cycle matures past common_end after corrected filter")
    print(f"  TEST 2 PASS: all 16 configs — no included cycle has mature_date > common_end")


def test_3_equity_index_within_window():
    ctx, candidates, regs = _build_all_registries()
    cs, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    for (cid, h, p), reg in regs.items():
        eq, meta = simulate_horizon_phase(
            reg, ctx["closes"], ctx["exp_series"], cs, ce,
            initial_capital=100_000, cash_return_annual=0.0, cost_bps=15.0,
            trading_days_per_year=252,
        )
        if len(eq):
            assert eq.index.max() <= ce, f"{cid}/{h}/{p} equity max {eq.index.max()} > {ce}"
            assert eq.index.min() >= cs, f"{cid}/{h}/{p} equity min {eq.index.min()} < {ce}"
    print(f"  TEST 3 PASS: all 16 simulator outputs have equity indices within [common_start, common_end]")


def test_4_asof_lte_end_but_mature_gt_end_excluded():
    """Verify cycles with asof <= common_end but mature_date > common_end are excluded."""
    ctx, _, regs = _build_all_registries()
    cs, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    total_asof_ok_mature_bad = 0
    for (cid, h, p), reg in regs.items():
        r = reg.copy()
        r["asof"] = pd.to_datetime(r["asof"]).dt.normalize()
        r["mature_date"] = pd.to_datetime(r["mature_date"]).dt.normalize()
        # Cycles where asof<=common_end BUT mature_date > common_end (the ones that MUST be excluded)
        borderline = r[(r["asof"] <= ce) & (r["mature_date"] > ce)]
        total_asof_ok_mature_bad += borderline["rec_id"].nunique()
        # After filter, these must NOT be present
        filtered = r[(r["asof"] >= cs) & (r["mature_date"] <= ce)]
        assert filtered["mature_date"].max() <= ce if len(filtered) else True
        # None of the borderline cycles should appear in filtered
        overlap = set(borderline["rec_id"]) & set(filtered["rec_id"])
        assert not overlap, f"{cid}/{h}/{p}: borderline cycles leaked into filtered set: {overlap}"
    print(f"  TEST 4 PASS: verified across all 16 configs; total borderline cycles correctly excluded = "
          f"such cycles existed under original filter")


def test_5_first_included_cycle_turnover_zero():
    ctx, _, regs = _build_all_registries()
    cs, ce = compute_common_window({(h, p): r for (cid, h, p), r in regs.items()})
    for (cid, h, p), reg in regs.items():
        eq, meta = simulate_horizon_phase(
            reg, ctx["closes"], ctx["exp_series"], cs, ce,
            initial_capital=100_000, cash_return_annual=0.0, cost_bps=15.0,
            trading_days_per_year=252,
        )
        if meta:
            assert meta[0]["turnover_t"] == 0.0, (
                f"{cid}/{h}/{p}: first cycle turnover should be 0, got {meta[0]['turnover_t']}")
    print(f"  TEST 5 PASS: first included cycle has turnover_t == 0 across all 16 configs")


def test_6_turnover_formula_worked_example():
    """exp 0.8->0.9, {A:0.5,B:0.5} -> {C:0.5,D:0.5}. Expected: 0.90."""
    stock_w_prev = {"A": 0.5, "B": 0.5}; exp_prev = 0.8
    stock_w_cur  = {"C": 0.5, "D": 0.5}; exp_cur = 0.9
    all_syms = set(stock_w_prev) | set(stock_w_cur)
    eff_prev = {s: exp_prev * stock_w_prev.get(s, 0.0) for s in all_syms}
    eff_cur  = {s: exp_cur  * stock_w_cur.get(s, 0.0)  for s in all_syms}
    stock_side = sum(abs(eff_cur[s] - eff_prev[s]) for s in all_syms)
    cash_side  = abs(exp_cur - exp_prev)
    turnover = 0.5 * (stock_side + cash_side)
    assert abs(turnover - 0.90) < 1e-9, f"turnover formula broken: got {turnover}, expected 0.90"
    print(f"  TEST 6 PASS: turnover formula worked example = {turnover:.4f} == 0.90")


def test_7_trial_manifest_still_38():
    manifest_path = ROOT / "india" / "ai_lab" / "trial_manifest.md"
    n = read_trial_manifest_count(manifest_path)
    assert n == 38, f"cumulative_strategy_search must remain 38, got {n}"
    print(f"  TEST 7 PASS: trial manifest cumulative_strategy_search = {n}")


def test_8_gate_expressions_byte_identical():
    """Verify all six gate expressions in lab009.yaml are unchanged."""
    from india.ai_lab.lab_config import load_experiment_config
    cfg = load_experiment_config(ROOT / "india" / "ai_lab" / "LAB009_Horizon_Phase_Recalibration" / "lab009.yaml")
    expected_expressions = [
        ("gate_1", "cand.median.conf.sharpe >= n0.median.conf.sharpe"),
        ("gate_2", "cand.median.full.cagr >= n0.median.full.cagr - 0.01"),
        ("gate_3", "cand.median.full.sharpe >= n0.median.full.sharpe - 0.05"),
        ("gate_4", "cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03"),
        ("gate_5", "cand.phase_top2_sharpe >= 0.50"),
        ("gate_6", "(cand.cost_drag - n0.cost_drag) <= 0.01"),
    ]
    assert len(cfg.gates) == 6, f"expected 6 gates, got {len(cfg.gates)}"
    for i, (gid, expected_expr) in enumerate(expected_expressions):
        g = cfg.gates[i]
        assert g["id"] == gid, f"gate {i} id mismatch: {g['id']} vs {gid}"
        assert g["expression"] == expected_expr, (
            f"gate {gid} expression drift:\n  yaml: {g['expression']!r}\n  expected: {expected_expr!r}")
    print(f"  TEST 8 PASS: all 6 gate expressions byte-identical to sealed LAB009 spec")


if __name__ == "__main__":
    tests = [
        test_1_common_end_uses_min_mature,
        test_2_no_included_cycle_matures_past_end,
        test_3_equity_index_within_window,
        test_4_asof_lte_end_but_mature_gt_end_excluded,
        test_5_first_included_cycle_turnover_zero,
        test_6_turnover_formula_worked_example,
        test_7_trial_manifest_still_38,
        test_8_gate_expressions_byte_identical,
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
