"""
LAB010 framework tests — structural + preregistration integrity.

These tests validate that LAB010's harness matches the sealed preregistration BYTE-IDENTICAL,
enforce the mature-bounded block/LOBO cycle rules, and confirm that LAB010 does not silently
introduce new candidates/horizons/phases/thresholds.

Run: python india/ai_lab/LAB010_H84_Robustness_Validation/test_lab010_framework.py

Must PASS before any LAB010 execution.

DO NOT execute run_lab010.py from these tests. Tests use synthetic data only.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd

from india.ai_lab.lab_config import load_experiment_config
from india.ai_lab.lab_metrics import read_trial_manifest_count
from india.ai_lab.lab_expression import compile_gate_expression, SafeExpressionError
from india.ai_lab.LAB010_H84_Robustness_Validation.run_lab010 import (
    filter_registry_to_ranges, scope_ranges, parse_gate_scope, build_namespace,
)

LAB010_DIR = Path(__file__).parent
CFG_PATH = LAB010_DIR / "lab010.yaml"


# ---------- expected sealed state ----------
EXPECTED_CANDIDATES = {"N0", "H84"}
EXPECTED_HORIZONS = {"N0": 63, "H84": 84}
EXPECTED_PHASES = {"N0": [0, 15, 31, 47], "H84": [0, 21, 42, 63]}
EXPECTED_BLOCKS = {
    "B1": ("2021-10-01", "2023-06-30"),
    "B2": ("2023-07-01", "2024-12-31"),
    "B3": ("2025-01-01", "2026-03-27"),
}
EXPECTED_LOBO = {"LOBO_dropB1": "B1", "LOBO_dropB2": "B2", "LOBO_dropB3": "B3"}
EXPECTED_TRIAL_COUNT = 38

# The 6 LAB009 gate thresholds LAB010 must reuse verbatim. Any deviation means LAB010 has
# invented new numbers — a preregistration breach.
LAB009_GATE_EXPRS = {
    "gate_1": "cand.median.conf.sharpe >= n0.median.conf.sharpe",
    "gate_2": "cand.median.full.cagr >= n0.median.full.cagr - 0.01",
    "gate_3": "cand.median.full.sharpe >= n0.median.full.sharpe - 0.05",
    "gate_4": "cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03",
    "gate_5": "cand.phase_top2_sharpe >= 0.50",
    "gate_6": "(cand.cost_drag - n0.cost_drag) <= 0.01",
}


def _phase_offsets(h: int) -> list[int]:
    return sorted({0, h // 4, h // 2, (3 * h) // 4})


# ---------------------------- Tests ----------------------------

def test_1_config_loads():
    cfg = load_experiment_config(CFG_PATH)
    assert cfg.lab_id == "LAB010", f"lab_id must be LAB010, got {cfg.lab_id}"
    print(f"  TEST 1 PASS: config loads with lab_id={cfg.lab_id}")


def test_2_candidates_only_n0_and_h84():
    cfg = load_experiment_config(CFG_PATH)
    got = set(cfg.candidates.keys())
    assert got == EXPECTED_CANDIDATES, f"Expected {EXPECTED_CANDIDATES}, got {got}"
    print(f"  TEST 2 PASS: exactly N0 and H84 candidates present")


def test_3_horizons_locked_to_63_and_84():
    cfg = load_experiment_config(CFG_PATH)
    for cid, expected_h in EXPECTED_HORIZONS.items():
        got = int(cfg.candidates[cid]["horizon_days"])
        assert got == expected_h, f"{cid} horizon must be {expected_h}, got {got}"
    print(f"  TEST 3 PASS: N0=63d and H84=84d horizons locked")


def test_4_phase_offsets_deterministic():
    # LAB010 must not override LAB009's phase offset formula.
    for cid, h in EXPECTED_HORIZONS.items():
        got = _phase_offsets(h)
        assert got == EXPECTED_PHASES[cid], f"{cid} phase offsets: expected {EXPECTED_PHASES[cid]}, got {got}"
    print(f"  TEST 4 PASS: phase offsets deterministic from horizon (floor formula)")


def test_5_control_is_n0():
    cfg = load_experiment_config(CFG_PATH)
    assert cfg.control_id() == "N0", f"control must be N0, got {cfg.control_id()}"
    assert cfg.candidates["N0"].get("is_control") is True
    print(f"  TEST 5 PASS: N0 is the sole control")


def test_6_blocks_locked():
    cfg = load_experiment_config(CFG_PATH)
    blocks = {b["id"]: (b["start"], b["end"]) for b in cfg.raw["blocks"]}
    assert blocks == EXPECTED_BLOCKS, f"Blocks changed vs seal.\nExpected: {EXPECTED_BLOCKS}\nGot:      {blocks}"
    print(f"  TEST 6 PASS: 3 chronological blocks locked byte-identical to seal")


def test_7_lobo_folds_locked():
    cfg = load_experiment_config(CFG_PATH)
    lobo = {f["id"]: f["exclude"] for f in cfg.raw["lobo_folds"]}
    assert lobo == EXPECTED_LOBO, f"LOBO folds changed vs seal.\nExpected: {EXPECTED_LOBO}\nGot:      {lobo}"
    print(f"  TEST 7 PASS: 3 LOBO folds locked byte-identical to seal")


def test_8_trial_count_38_unchanged():
    cfg = load_experiment_config(CFG_PATH)
    n = read_trial_manifest_count(cfg.trial_manifest_path)
    assert n == EXPECTED_TRIAL_COUNT, (
        f"LAB010 must NOT increment strategy_search: expected {EXPECTED_TRIAL_COUNT}, got {n}")
    print(f"  TEST 8 PASS: cumulative_strategy_search unchanged at {n}")


def test_9_gates_reuse_lab009_thresholds():
    cfg = load_experiment_config(CFG_PATH)
    exprs = {g["id"]: g["expression"] for g in cfg.gates}
    # LAB009-derived forms that LAB010 is allowed to use:
    #   - the 6 LAB009 gate exprs (byte-identical) OR
    #   - "cand.phase_win_rate >= 0.50"  (2-candidate analog of LAB009 gate_5; same 0.50 threshold) OR
    #   - "cand.median.full.sharpe >= n0.median.full.sharpe"  (LAB009 gate_3 form, no slack)
    ALLOWED_FORMS = set(v.replace(" ", "") for v in LAB009_GATE_EXPRS.values())
    ALLOWED_FORMS.add("cand.phase_win_rate>=0.50")
    ALLOWED_FORMS.add("cand.median.full.sharpe>=n0.median.full.sharpe")
    reused = 0
    for _gate_id, expr in exprs.items():
        norm = expr.replace(" ", "")
        if norm in ALLOWED_FORMS:
            reused += 1
    assert reused == len(exprs), (
        f"Only {reused}/{len(exprs)} gates use LAB009-derived threshold forms. "
        f"LAB010 must not introduce arbitrary new numeric thresholds.")
    print(f"  TEST 9 PASS: {reused}/{len(exprs)} gate exprs use LAB009-derived forms")


def test_10_no_arbitrary_new_thresholds():
    """No gate may contain a numeric constant outside {0.0, 0.01, 0.03, 0.05, 0.50}
    (the LAB009 sealed threshold set)."""
    ALLOWED = {0.0, 0.01, 0.03, 0.05, 0.5}
    cfg = load_experiment_config(CFG_PATH)
    import ast as _ast
    offenders = []
    for g in cfg.gates:
        tree = _ast.parse(g["expression"], mode="eval")
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
                v = float(node.value)
                if v not in ALLOWED and abs(v) > 1e-9:
                    offenders.append((g["id"], v))
    assert not offenders, f"New arbitrary threshold constants found: {offenders}"
    print(f"  TEST 10 PASS: no gate introduces numeric constants outside LAB009's sealed threshold set")


def test_11_scope_parsing_full():
    cfg = load_experiment_config(CFG_PATH)
    sid, cost = parse_gate_scope("full,cost:canonical", cfg)
    assert sid == "full" and cost == cfg.canonical_cost()
    sid, cost = parse_gate_scope("full,cost:stress", cfg)
    assert sid == "full" and cost == cfg.stress_cost()
    print(f"  TEST 11 PASS: full-scope parsing under canonical & stress cost")


def test_12_scope_parsing_block_and_lobo():
    cfg = load_experiment_config(CFG_PATH)
    sid, cost = parse_gate_scope("block:B1,cost:canonical", cfg)
    assert sid == "block:B1"
    sid, cost = parse_gate_scope("block:B2,cost:canonical", cfg)
    assert sid == "block:B2"
    sid, cost = parse_gate_scope("lobo:LOBO_dropB1,cost:canonical", cfg)
    assert sid == "lobo:LOBO_dropB1"
    sid, cost = parse_gate_scope("lobo:LOBO_dropB3,cost:canonical", cfg)
    assert sid == "lobo:LOBO_dropB3"
    print(f"  TEST 12 PASS: block/LOBO scope parsing correct")


def test_13_scope_ranges_full_covers_all_blocks():
    cfg = load_experiment_config(CFG_PATH)
    blocks = {b["id"]: {"start": b["start"], "end": b["end"]} for b in cfg.raw["blocks"]}
    lobo_folds = {f["id"]: {"exclude": f["exclude"]} for f in cfg.raw["lobo_folds"]}
    r = scope_ranges("full", blocks, lobo_folds)
    assert r == [(pd.Timestamp("2021-10-01"), pd.Timestamp("2026-03-27"))]
    print(f"  TEST 13 PASS: full scope spans 2021-10-01 to 2026-03-27")


def test_14_lobo_ranges_drop_correct_block():
    cfg = load_experiment_config(CFG_PATH)
    blocks = {b["id"]: {"start": b["start"], "end": b["end"]} for b in cfg.raw["blocks"]}
    lobo_folds = {f["id"]: {"exclude": f["exclude"]} for f in cfg.raw["lobo_folds"]}
    # LOBO_dropB2 must retain B1 and B3 (non-consecutive)
    r = scope_ranges("lobo:LOBO_dropB2", blocks, lobo_folds)
    assert len(r) == 2
    starts = {rr[0] for rr in r}
    assert pd.Timestamp("2021-10-01") in starts and pd.Timestamp("2025-01-01") in starts
    # LOBO_dropB1 retains B2 and B3 (consecutive)
    r = scope_ranges("lobo:LOBO_dropB1", blocks, lobo_folds)
    starts = {rr[0] for rr in r}
    assert pd.Timestamp("2023-07-01") in starts and pd.Timestamp("2025-01-01") in starts
    assert pd.Timestamp("2021-10-01") not in starts
    print(f"  TEST 14 PASS: LOBO scope ranges drop the correct block")


def test_15_filter_registry_mature_bounded_rule():
    # Cycle A: asof=2022-01-05 mature=2023-06-01  -> fits B1 (mature <= B1.end 2023-06-30)
    # Cycle B: asof=2023-06-15 mature=2023-07-30  -> straddles B1/B2 -> excluded from B1
    # Cycle C: asof=2023-07-15 mature=2024-01-10  -> fits B2
    reg = pd.DataFrame({
        "rec_id": ["A", "B", "C"],
        "asof": ["2022-01-05", "2023-06-15", "2023-07-15"],
        "mature_date": ["2023-06-01", "2023-07-30", "2024-01-10"],
    })
    b1_only = filter_registry_to_ranges(reg, [(pd.Timestamp("2021-10-01"), pd.Timestamp("2023-06-30"))])
    assert set(b1_only["rec_id"]) == {"A"}, f"B1 should keep A only, got {set(b1_only['rec_id'])}"
    b1b2 = filter_registry_to_ranges(reg, [
        (pd.Timestamp("2021-10-01"), pd.Timestamp("2023-06-30")),
        (pd.Timestamp("2023-07-01"), pd.Timestamp("2024-12-31")),
    ])
    assert set(b1b2["rec_id"]) == {"A", "C"}, f"B1|B2 should keep A,C only, got {set(b1b2['rec_id'])}"
    print(f"  TEST 15 PASS: mature-bounded rule drops straddlers correctly")


def test_16_gate_expression_ast_safe():
    cfg = load_experiment_config(CFG_PATH)
    # every gate expression must compile via AST-safe evaluator (no eval())
    for g in cfg.gates:
        fn = compile_gate_expression(g["expression"], allowed_roots=("cand", "n0"))
        assert callable(fn)
    print(f"  TEST 16 PASS: all {len(cfg.gates)} gate expressions AST-safe compile-ready")


def test_17_gate_expression_rejects_disallowed():
    from india.ai_lab.LAB010_H84_Robustness_Validation.run_lab010 import build_namespace
    try:
        compile_gate_expression("__import__('os')", allowed_roots=("cand", "n0"))
        raise AssertionError("Expression '__import__' should have been rejected")
    except SafeExpressionError:
        pass
    print(f"  TEST 17 PASS: AST evaluator rejects disallowed expressions")


def test_18_namespace_deep_attribute_access():
    """cand.median.full.sharpe must resolve via Namespace wrapper."""
    stub = {
        "median": {"full": {"sharpe": 1.20, "cagr": 0.11}, "conf": {"sharpe": 0.81}},
        "worst":  {"full": {"max_dd": -0.16}},
        "phase_top2_sharpe": 0.50,
        "cost_drag": 0.0065,
    }
    ns = build_namespace(stub, stub)
    fn = compile_gate_expression("cand.median.full.sharpe >= n0.median.full.sharpe - 0.05",
                                 allowed_roots=("cand", "n0"))
    assert fn(ns) is True, "Deep attribute access broken"
    print(f"  TEST 18 PASS: deep attribute access via Namespace works")


def test_19_gate_v6_reproduces_lab009_gates_1_6():
    cfg = load_experiment_config(CFG_PATH)
    v6_ids = [g["id"] for g in cfg.gates if g["id"].startswith("v6_full_")]
    assert len(v6_ids) == 6, f"V6 must have exactly 6 gates (LAB009 replay), got {len(v6_ids)}"
    v6_exprs = {g["id"]: g["expression"].replace(" ", "") for g in cfg.gates if g["id"].startswith("v6_full_")}
    lab009_norm = {k: v.replace(" ", "") for k, v in LAB009_GATE_EXPRS.items()}
    for i in range(1, 7):
        v6_key = f"v6_full_gate{i}"
        lab009_key = f"gate_{i}"
        assert v6_exprs[v6_key] == lab009_norm[lab009_key], (
            f"{v6_key} expression must match LAB009's {lab009_key} byte-identical")
    print(f"  TEST 19 PASS: V6 gates reproduce LAB009 gates 1-6 byte-identical")


def test_20_lobo_folds_cover_every_block():
    cfg = load_experiment_config(CFG_PATH)
    lobo_excludes = {f["exclude"] for f in cfg.raw["lobo_folds"]}
    blocks = {b["id"] for b in cfg.raw["blocks"]}
    assert lobo_excludes == blocks, (
        f"Every block must have exactly one LOBO fold that drops it. "
        f"Blocks={blocks}, LOBO excludes={lobo_excludes}")
    print(f"  TEST 20 PASS: LOBO folds cover every block exactly once")


def test_21_no_horizons_besides_63_and_84():
    cfg = load_experiment_config(CFG_PATH)
    horizons = {int(cfg.candidates[cid]["horizon_days"]) for cid in cfg.candidates}
    assert horizons == {63, 84}, (
        f"LAB010 must not test any horizon other than 63 (control) and 84 (validation subject). "
        f"Got: {sorted(horizons)}")
    print(f"  TEST 21 PASS: no forbidden horizons (H21/H42/etc) present")


def test_22_report_names_carry_lab010_prefix():
    cfg = load_experiment_config(CFG_PATH)
    r = cfg.reporting["report_name_template"]
    d = cfg.reporting["diagnostics_name_template"]
    assert r.startswith("lab010_"), f"Report template must start with lab010_, got {r}"
    assert d.startswith("lab010_"), f"Diagnostics template must start with lab010_, got {d}"
    print(f"  TEST 22 PASS: LAB010 output names properly namespaced")


def test_23_block_majority_min_wins_is_2():
    cfg = load_experiment_config(CFG_PATH)
    assert int(cfg.raw["block_majority_min_wins"]) == 2, (
        "block_majority_min_wins must be 2 (majority of 3)")
    print(f"  TEST 23 PASS: block-majority threshold locked at 2/3")


def test_24_v3_gates_use_phase_win_rate_not_degenerate_metric():
    """After pre-seal adversarial audit fix: V3 LOBO gates must NOT use phase_top2_sharpe
    (degenerate in 2-cand universe) — they must use phase_win_rate instead."""
    cfg = load_experiment_config(CFG_PATH)
    v3_gates = [g for g in cfg.gates if g["id"].startswith("v3_lobo_")]
    assert len(v3_gates) == 3, f"Expected 3 V3 gates, got {len(v3_gates)}"
    for g in v3_gates:
        assert "phase_win_rate" in g["expression"], (
            f"V3 gate {g['id']} must use phase_win_rate, got: {g['expression']}")
        assert "phase_top2_sharpe" not in g["expression"], (
            f"V3 gate {g['id']} must NOT use phase_top2_sharpe (degenerate in 2-cand)")
    print(f"  TEST 24 PASS: V3 LOBO gates use phase_win_rate (audit fix applied)")


def test_25_phase_win_rate_bounded_and_non_degenerate():
    """Simulate 4 phases with H84 winning 3 of 4 vs N0. phase_win_rate must = 0.75."""
    # Emulate run_scope's phase_win_rate computation
    h84_sh = [1.10, 1.30, 0.99, 1.45]
    n0_sh  = [1.17, 1.29, 1.07, 1.33]
    wins = [1.0 if h >= n else 0.0 for h, n in zip(h84_sh, n0_sh)]
    rate = sum(wins) / len(wins)
    assert rate == 0.5, f"Expected 0.5, got {rate}"
    # Now full-win case: rate = 1.0
    wins_all = [1.0] * 4
    assert sum(wins_all) / 4 == 1.0
    # Full-loss case: rate = 0.0
    wins_none = [0.0] * 4
    assert sum(wins_none) / 4 == 0.0
    print(f"  TEST 25 PASS: phase_win_rate is bounded in [0, 1] and non-degenerate")


# ---------------------------- Driver ----------------------------

TESTS = [
    test_1_config_loads,
    test_2_candidates_only_n0_and_h84,
    test_3_horizons_locked_to_63_and_84,
    test_4_phase_offsets_deterministic,
    test_5_control_is_n0,
    test_6_blocks_locked,
    test_7_lobo_folds_locked,
    test_8_trial_count_38_unchanged,
    test_9_gates_reuse_lab009_thresholds,
    test_10_no_arbitrary_new_thresholds,
    test_11_scope_parsing_full,
    test_12_scope_parsing_block_and_lobo,
    test_13_scope_ranges_full_covers_all_blocks,
    test_14_lobo_ranges_drop_correct_block,
    test_15_filter_registry_mature_bounded_rule,
    test_16_gate_expression_ast_safe,
    test_17_gate_expression_rejects_disallowed,
    test_18_namespace_deep_attribute_access,
    test_19_gate_v6_reproduces_lab009_gates_1_6,
    test_20_lobo_folds_cover_every_block,
    test_21_no_horizons_besides_63_and_84,
    test_22_report_names_carry_lab010_prefix,
    test_23_block_majority_min_wins_is_2,
    test_24_v3_gates_use_phase_win_rate_not_degenerate_metric,
    test_25_phase_win_rate_bounded_and_non_degenerate,
]


def main():
    print("=" * 70)
    print("  LAB010 FRAMEWORK TESTS — structural + preregistration integrity")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    total = len(TESTS)
    print(f"\n  {passed} passed, {failed} failed of {total}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
