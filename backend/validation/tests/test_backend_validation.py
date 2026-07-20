"""Regression tests for the shared backend/validation framework.

Runs without external data: constructs synthetic dataset specs +
tiny temp files, exercises each validator, verifies verdicts + result
shape. Also runs the India + USA runners on the live repo (they must
at least parse and emit valid JSON).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.validation.base import Validator, ValidationResult, Verdict, Severity, Issue    # noqa: E402
from backend.validation.freshness import FreshnessValidator                                    # noqa: E402
from backend.validation.schema import SchemaValidator                                          # noqa: E402
from backend.validation.completeness import CompletenessValidator                              # noqa: E402
from backend.validation.quality import QualityValidator                                        # noqa: E402
from backend.validation.lineage import LineageValidator                                        # noqa: E402
from backend.validation.confidence import ConfidenceAggregator                                 # noqa: E402
from backend.validation.pipeline import BackendValidationPipeline                              # noqa: E402


# ── Unit tests for the validators ─────────────────────────────────

def test_freshness_pass_on_fresh_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "fresh.parquet"
        pd.DataFrame({"x": [1, 2, 3]}).to_parquet(p)
        r = FreshnessValidator().validate({"name": "fresh", "path": "fresh.parquet",
                                             "freshness_sla_trading_days": 1}, root)
        assert r.verdict == Verdict.PASS, f"expected PASS got {r.verdict}"
        print("  [OK] freshness PASS on fresh file")


def test_freshness_fail_on_missing_required():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        r = FreshnessValidator().validate({"name": "missing", "path": "nope.parquet"}, root)
        assert r.verdict == Verdict.FAIL, f"expected FAIL got {r.verdict}"
        print("  [OK] freshness FAIL on missing required file")


def test_freshness_na_on_missing_optional():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        r = FreshnessValidator().validate({"name": "missing", "path": "nope.parquet",
                                             "optional": True}, root)
        assert r.verdict == Verdict.NOT_APPLICABLE
        print("  [OK] freshness NA on missing optional file")


def test_schema_pass_and_fail():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "d.parquet"
        pd.DataFrame({"a": [1], "b": [2], "c": [3]}).to_parquet(p)
        r_pass = SchemaValidator().validate({
            "name": "d", "path": "d.parquet",
            "schema": {"required_columns": ["a", "b"]}}, root)
        r_fail = SchemaValidator().validate({
            "name": "d", "path": "d.parquet",
            "schema": {"required_columns": ["a", "b", "missing_col"]}}, root)
        assert r_pass.verdict == Verdict.PASS
        assert r_fail.verdict == Verdict.FAIL
        assert "missing_col" in str(r_fail.issues[0].evidence)
        print("  [OK] schema PASS + FAIL")


def test_schema_json():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "d.json"
        p.write_text(json.dumps({"engine": "x", "reports": []}), encoding="utf-8")
        r = SchemaValidator().validate({
            "name": "d", "path": "d.json",
            "schema": {"required_keys": ["engine", "reports"]}}, root)
        assert r.verdict == Verdict.PASS
        print("  [OK] schema PASS on JSON")


def test_completeness_row_count_and_nulls():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "d.parquet"
        pd.DataFrame({"a": [1, 2, None, 4], "b": [1, 2, 3, 4]}).to_parquet(p)
        r = CompletenessValidator().validate({
            "name": "d", "path": "d.parquet",
            "completeness": {"min_rows": 10,
                              "max_null_pct_per_column": {"a": 0.1}}}, root)
        assert r.verdict == Verdict.WARNING
        assert r.evidence["n_rows"] == 4
        assert r.evidence["null_pct"]["a"] == 0.25
        print("  [OK] completeness WARN on low row count + high null pct")


def test_quality_no_negatives_and_duplicates():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "d.parquet"
        pd.DataFrame({"ticker": ["A", "A", "B"], "date": ["d1", "d1", "d1"],
                       "close": [100, -1, 200]}).to_parquet(p)
        r = QualityValidator().validate({
            "name": "d", "path": "d.parquet",
            "quality": {"dedupe_on": ["ticker", "date"], "no_negatives": ["close"]}
        }, root)
        assert r.verdict == Verdict.FAIL
        assert r.evidence["n_negatives"]["close"] == 1
        print("  [OK] quality FAIL on negatives + duplicates")


def test_confidence_aggregator():
    agg = ConfidenceAggregator()
    results = [
        ValidationResult(validator="freshness",   dataset="d", verdict=Verdict.PASS, confidence=1.0),
        ValidationResult(validator="schema",      dataset="d", verdict=Verdict.WARNING, confidence=0.7,
                          issues=[Issue(Severity.WARNING, "x")]),
        ValidationResult(validator="completeness", dataset="d", verdict=Verdict.PASS, confidence=1.0),
    ]
    r = agg.aggregate("d", results)
    assert r.verdict == Verdict.WARNING
    assert 0.5 < r.confidence < 1.0
    print("  [OK] confidence aggregator weights + rolls up verdict")


def test_lineage_pass_on_external_producer():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        r = LineageValidator().validate({"name": "d", "path": "d.parquet",
                                            "producer": "yfinance"}, root)
        assert r.verdict == Verdict.PASS
        print("  [OK] lineage PASS on external producer label")


def test_pipeline_end_to_end():
    """Full pipeline over a synthetic mini-registry."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p1 = root / "good.parquet"; p2 = root / "bad.parquet"
        pd.DataFrame({"x": [1, 2, 3]}).to_parquet(p1)
        pd.DataFrame({"x": [-1, 2, 3]}).to_parquet(p2)
        datasets = [
            {"name": "good", "path": "good.parquet", "producer": "external",
             "schema": {"required_columns": ["x"]}},
            {"name": "bad",  "path": "bad.parquet",  "producer": "external",
             "schema": {"required_columns": ["x"]},
             "quality": {"no_negatives": ["x"]}},
        ]
        pipeline = BackendValidationPipeline("test", datasets, root)
        result = pipeline.run()
        assert result["n_datasets"] == 2
        assert result["counts"]["PASS"] == 1
        assert result["counts"]["FAIL"] == 1
        assert result["verdict"] == "FAIL"
        summary = pipeline.summary(result)
        assert summary["market"] == "test"
        print("  [OK] pipeline end-to-end: 2 datasets · 1 PASS · 1 FAIL")


# ── Integration tests against live repo ────────────────────────────

def test_india_runner_runs_and_emits_valid_json():
    """India runner completes without crashing and emits parseable JSON."""
    result = subprocess.run(
        [sys.executable, "india/backend_validation/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    # Exit code may be 1 (FAIL verdict is expected for India), just verify it ran + emitted JSON
    assert result.returncode in (0, 1), f"unexpected exit code: {result.returncode}\n{result.stderr[:500]}"
    bv = json.loads((_ROOT / "reports" / "backend_validation.json").read_text(encoding="utf-8"))
    assert bv["engine"] == "backend_validation"
    assert bv["market"] == "india"
    assert bv["n_datasets"] > 0
    assert "verdict" in bv
    print(f"  [OK] india runner: n_datasets={bv['n_datasets']} verdict={bv['verdict']}")


def test_usa_runner_runs_and_emits_valid_json():
    result = subprocess.run(
        [sys.executable, "usa/backend_validation/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert result.returncode in (0, 1), f"unexpected exit code: {result.returncode}\n{result.stderr[:500]}"
    bv = json.loads((_ROOT / "usa" / "reports" / "backend_validation.json").read_text(encoding="utf-8"))
    assert bv["engine"] == "backend_validation"
    assert bv["market"] == "usa"
    assert bv["n_datasets"] > 0
    print(f"  [OK] usa runner:   n_datasets={bv['n_datasets']} verdict={bv['verdict']}")


TESTS = [
    test_freshness_pass_on_fresh_file,
    test_freshness_fail_on_missing_required,
    test_freshness_na_on_missing_optional,
    test_schema_pass_and_fail,
    test_schema_json,
    test_completeness_row_count_and_nulls,
    test_quality_no_negatives_and_duplicates,
    test_confidence_aggregator,
    test_lineage_pass_on_external_producer,
    test_pipeline_end_to_end,
    test_india_runner_runs_and_emits_valid_json,
    test_usa_runner_runs_and_emits_valid_json,
]


def main() -> int:
    import io
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("=" * 70)
    print("  BACKEND VALIDATION FRAMEWORK · Regression Tests")
    print("=" * 70)
    n_pass = 0; n_fail = 0
    for t in TESTS:
        try:
            t()
            n_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            n_fail += 1
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}")
            n_fail += 1
    print()
    print(f"  {n_pass} passed, {n_fail} failed of {len(TESTS)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
