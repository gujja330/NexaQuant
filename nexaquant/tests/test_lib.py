"""Unit tests for nexaquant/lib/ shared utilities.

Every test is fully deterministic and hermetic. Uses temp dirs; never touches
production files, LAB evidence, MON001 ledger, or the aegis_registry.

Run:
    python nexaquant/tests/test_lib.py
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexaquant.lib import paths, env_loader, metrics, logging_setup, timing


# ----------------------------- paths ---------------------------------


def test_1_repo_root_discovered_correctly():
    assert paths.REPO_ROOT.name == "prism", (
        f"repo root should end in 'prism', got {paths.REPO_ROOT}")
    assert (paths.REPO_ROOT / "run_daily.bat").exists()
    assert (paths.REPO_ROOT / "india").is_dir()
    print("  TEST 1 PASS: repo root discovered via run_daily.bat marker")


def test_2_wellknown_paths_resolve():
    assert paths.INDIA_DIR.is_dir()
    assert paths.DATA_DIR.is_dir()
    assert paths.AI_LAB_DIR.is_dir()
    assert paths.MON001_DIR.is_dir()
    assert paths.AEGIS_REGISTRY_CSV.exists()
    assert paths.TRIAL_MANIFEST.exists()
    print("  TEST 2 PASS: all well-known repo paths resolve")


def test_3_repo_relative_inside_repo():
    p = paths.INDIA_DIR / "recommendation_registry.py"
    rel = paths.repo_relative(p)
    assert str(rel) == "india/recommendation_registry.py" or \
           str(rel) == "india\\recommendation_registry.py"
    print("  TEST 3 PASS: repo_relative computes relative path inside repo")


def test_4_repo_relative_outside_repo_returns_absolute():
    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp).resolve() / "some_file.txt"
        outside.write_text("test")
        result = paths.repo_relative(outside)
        assert result.is_absolute()
    print("  TEST 4 PASS: repo_relative returns absolute path outside repo")


def test_5_ensure_dir_creates_and_returns():
    with tempfile.TemporaryDirectory() as tmp:
        new_dir = Path(tmp) / "a" / "b" / "c"
        result = paths.ensure_dir(new_dir)
        assert result.is_dir() and result == new_dir
    print("  TEST 5 PASS: ensure_dir creates nested directory")


# ----------------------------- env_loader ---------------------------------


def test_6_parse_env_file_basic():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / ".env"
        p.write_text('KEY1=value1\nKEY2="quoted"\n# comment\n\nKEY3=\'single-quoted\'\n')
        result = env_loader.parse_env_file(p)
        assert result == {"KEY1": "value1", "KEY2": "quoted", "KEY3": "single-quoted"}
    print("  TEST 6 PASS: parse_env_file handles quotes, comments, blank lines")


def test_7_parse_env_file_missing():
    try:
        env_loader.parse_env_file("/tmp/does_not_exist_12345.env")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")
    print("  TEST 7 PASS: parse_env_file raises FileNotFoundError")


def test_8_load_env_files_existing_env_wins_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / ".env"
        p.write_text("ENG001_TEST_KEY=from_file\n")
        os.environ["ENG001_TEST_KEY"] = "from_os"
        try:
            env_loader.load_env_files(p)
            assert os.environ["ENG001_TEST_KEY"] == "from_os", \
                "default behaviour: existing os.environ wins"
        finally:
            del os.environ["ENG001_TEST_KEY"]
    print("  TEST 8 PASS: existing os.environ wins over file")


def test_9_load_env_files_override_true():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / ".env"
        p.write_text("ENG001_TEST_KEY=from_file\n")
        os.environ["ENG001_TEST_KEY"] = "from_os"
        try:
            env_loader.load_env_files(p, override=True)
            assert os.environ["ENG001_TEST_KEY"] == "from_file"
        finally:
            del os.environ["ENG001_TEST_KEY"]
    print("  TEST 9 PASS: override=True overwrites os.environ")


def test_10_load_env_files_missing_paths_silently_skipped():
    result = env_loader.load_env_files("/tmp/no1.env", "/tmp/no2.env")
    assert result == {}
    print("  TEST 10 PASS: load_env_files silently skips missing paths")


# ----------------------------- metrics ---------------------------------


def test_11_sharpe_deterministic():
    rets = pd.Series([0.01, -0.005, 0.008, 0.002, -0.003, 0.006])
    s = metrics.sharpe(rets)
    assert not math.isnan(s)
    # Compare to hand computation
    manual = float(rets.mean() / (rets.std() + 1e-12) * math.sqrt(252))
    assert abs(s - manual) < 1e-9, f"sharpe {s} != manual {manual}"
    print(f"  TEST 11 PASS: sharpe({s:.4f}) matches hand computation")


def test_12_sharpe_edge_cases():
    assert math.isnan(metrics.sharpe([]))
    assert math.isnan(metrics.sharpe([0.01]))
    assert math.isnan(metrics.sharpe([0.005, 0.005, 0.005]))  # zero std
    print("  TEST 12 PASS: sharpe returns NaN on <2 obs or zero variance")


def test_13_max_drawdown_correct():
    eq = pd.Series([100, 110, 105, 95, 100, 90])
    dd = metrics.max_drawdown(eq)
    # Peak was 110, trough thereafter was 90 -> (90-110)/110 = -0.1818...
    expected = (90 - 110) / 110
    assert abs(dd - expected) < 1e-9, f"got {dd}, expected {expected}"
    print(f"  TEST 13 PASS: max_drawdown = {dd:.4f} matches expected")


def test_14_cagr_correct():
    # 100% growth over 1 year (252 trading days) -> 100% CAGR
    eq = pd.Series([100.0] + [100.0 * (1 + 0.693/252) ** i for i in range(1, 253)])
    c = metrics.cagr(eq)
    # exp(0.693) ~ 2; CAGR ~ 1.0
    assert abs(c - 1.0) < 0.02, f"got {c}"
    print(f"  TEST 14 PASS: cagr = {c:.4f} (~1.0 for 100% year)")


def test_15_ulcer_index_positive():
    eq = pd.Series([100, 110, 90, 100, 80, 100])
    ui = metrics.ulcer_index(eq)
    assert ui > 0 and math.isfinite(ui)
    print(f"  TEST 15 PASS: ulcer_index = {ui:.4f}")


def test_16_sortino_only_downside_denom():
    # Downside std requires >1 negative return; test with a healthy mix.
    rets = pd.Series([0.01, 0.02, 0.015, -0.03, 0.01, -0.02, 0.008, -0.01])
    s = metrics.sortino(rets)
    assert math.isfinite(s), f"got {s}"
    print(f"  TEST 16 PASS: sortino = {s:.4f}")


def test_17_hit_rate_bounded():
    assert metrics.hit_rate([0.01, -0.01, 0.02, -0.02, 0.005]) == 0.6
    assert math.isnan(metrics.hit_rate([]))
    print("  TEST 17 PASS: hit_rate correct on mixed sample")


def test_18_annualized_vol_scales_correctly():
    rets = pd.Series([0.01] * 100 + [-0.01] * 100)  # std ~0.01
    v = metrics.annualized_vol(rets)
    # std * sqrt(252) ~ 0.01 * 15.87 = 0.1587
    assert 0.10 < v < 0.20
    print(f"  TEST 18 PASS: annualized_vol = {v:.4f}")


# ----------------------------- logging_setup ---------------------------------


def test_19_logger_created_and_reused():
    log = logging_setup.get_logger("nexaquant.test.19")
    assert len(log.handlers) >= 1
    n0 = len(log.handlers)
    log2 = logging_setup.get_logger("nexaquant.test.19")
    assert log is log2
    assert len(log.handlers) == n0, "handlers should not stack on repeat call"
    print(f"  TEST 19 PASS: logger reused idempotently ({n0} handler(s))")


def test_20_logger_writes_to_file():
    import logging as _logging
    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "test.log"
        log = logging_setup.get_logger("nexaquant.test.20", log_file=log_file)
        log.info("ENG001 test line")
        # Close file handlers so Windows can read + delete the tmpdir.
        for h in list(log.handlers):
            h.flush()
            if isinstance(h, _logging.FileHandler):
                h.close()
                log.removeHandler(h)
        content = log_file.read_text(encoding="utf-8")
        assert "ENG001 test line" in content
    print("  TEST 20 PASS: logger writes to file handler")


# ----------------------------- timing ---------------------------------


def test_21_timed_decorator_records_and_returns():
    from nexaquant.lib.timing import timed
    sink: dict = {}

    @timed(sink=sink, label="my_task")
    def _work(x: int) -> int:
        return x * 2

    assert _work(21) == 42
    assert "my_task" in sink
    assert sink["my_task"] > 0
    print(f"  TEST 21 PASS: @timed recorded {sink['my_task']*1000:.2f}ms")


def test_22_time_block_context_manager():
    from nexaquant.lib.timing import time_block
    sink: dict = {}
    with time_block("block_x", sink=sink) as ctx:
        _ = sum(range(10000))
    assert sink["block_x"] > 0
    assert ctx["elapsed"] == sink["block_x"]
    print(f"  TEST 22 PASS: time_block recorded {sink['block_x']*1000:.2f}ms")


# ----------------------------- invariance guards ---------------------------------


def test_23_no_import_from_sealed_baseline_files():
    """The nexaquant.lib package must NOT import from any of the 5 MON001-sealed
    baseline files. Enforced by grep to make MON001 CONFIG_DRIFT impossible."""
    forbidden = ("india.recommendation_registry", "india.recommendation_generator",
                  "india.confidence_engine", "india.arjuna_v2", "india.data_nse")
    for py in (paths.REPO_ROOT / "nexaquant").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in forbidden:
            assert f"from {name}" not in text and f"import {name}" not in text, (
                f"{py} imports from sealed baseline {name}")
    print("  TEST 23 PASS: nexaquant/ does not import any MON001-sealed file")


def test_24_no_writes_to_ai_lab_or_monitoring():
    """The nexaquant/lib package must not write into ai_lab/ or monitoring/.
    Only the lib/ subtree is scanned; tests are allowed to reference these
    paths as part of read-only invariance checks."""
    lib_dir = paths.REPO_ROOT / "nexaquant" / "lib"
    for py in lib_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for danger in ("ai_lab/", "MON001_Forward_Validation/"):
            if danger in text:
                if py.name == "paths.py":
                    # Allowed: paths.py exposes MON001_DIR / AI_LAB_DIR as read-only
                    # anchors for downstream consumers.
                    continue
                raise AssertionError(f"{py} references {danger}")
    print("  TEST 24 PASS: nexaquant/lib does not reference lab/monitoring paths (except paths.py anchors)")


def test_25_production_constants_still_unchanged():
    reg = (paths.REPO_ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (paths.REPO_ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    manifest = paths.TRIAL_MANIFEST.read_text(encoding="utf-8", errors="ignore")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    assert "cumulative_strategy_search: 38" in manifest
    print("  TEST 25 PASS: HOLD=63, rebal=63, cumulative_strategy_search=38 unchanged")


TESTS = [
    test_1_repo_root_discovered_correctly,
    test_2_wellknown_paths_resolve,
    test_3_repo_relative_inside_repo,
    test_4_repo_relative_outside_repo_returns_absolute,
    test_5_ensure_dir_creates_and_returns,
    test_6_parse_env_file_basic,
    test_7_parse_env_file_missing,
    test_8_load_env_files_existing_env_wins_by_default,
    test_9_load_env_files_override_true,
    test_10_load_env_files_missing_paths_silently_skipped,
    test_11_sharpe_deterministic,
    test_12_sharpe_edge_cases,
    test_13_max_drawdown_correct,
    test_14_cagr_correct,
    test_15_ulcer_index_positive,
    test_16_sortino_only_downside_denom,
    test_17_hit_rate_bounded,
    test_18_annualized_vol_scales_correctly,
    test_19_logger_created_and_reused,
    test_20_logger_writes_to_file,
    test_21_timed_decorator_records_and_returns,
    test_22_time_block_context_manager,
    test_23_no_import_from_sealed_baseline_files,
    test_24_no_writes_to_ai_lab_or_monitoring,
    test_25_production_constants_still_unchanged,
]


def main():
    print("=" * 70)
    print("  ENG001 nexaquant/lib UNIT TESTS — 25 scenarios")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
