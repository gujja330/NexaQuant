"""
india/ai_lab/tests/test_lab_framework.py — deterministic framework tests.

Covers the 17 required scenarios from the operator's hardening spec. NO integration tests here
(no full backtest execution) — that lives in parity_check.py. These tests must run in seconds.

Run: python -m pytest india/ai_lab/tests/test_lab_framework.py -q
Or:  python india/ai_lab/tests/test_lab_framework.py  (uses a lightweight in-file runner if pytest is absent)
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# Lightweight pytest.raises replacement (pytest is optional; framework must be testable without it)
import re as _re
from contextlib import contextmanager


class _Raises:
    def __init__(self, exc_type, match=None):
        self.exc_type = exc_type
        self.match = match

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"expected {self.exc_type.__name__} to be raised, no exception occurred")
        if not issubclass(exc_type, self.exc_type):
            return False
        if self.match and not _re.search(self.match, str(exc_val)):
            raise AssertionError(
                f"exception {exc_type.__name__} raised but message {str(exc_val)!r} does not match {self.match!r}")
        return True


class pytest:  # noqa: N801 - namespace stub
    @staticmethod
    def raises(exc_type, match=None):
        return _Raises(exc_type, match)


from india.ai_lab.lab_config import load_experiment_config
from india.ai_lab.lab_expression import compile_gate_expression, SafeExpressionError
from india.ai_lab.lab_metrics import read_trial_manifest_count
from india.ai_lab import lab_runner as R


# ---------- helpers ----------

_MINIMAL_YAML = """
lab_id: LABTEST
lab_name: Test
preregistration_file: preregistration.md
trial_manifest: trial_manifest.md

simulation:
  registry_path: data/aegis_registry.csv
  initial_capital: 100000
  cash_returns_annual: [0.0, 0.06]
  cost_grid_bps: [15, 30, 50]
  trading_days_per_year: 252
  canonical_cost_bps: 15
  promotion_stress_cost_bps: 50

periods:
  discovery_end: "2023-10-13"
  confirmation_start: "2024-01-15"

stability:
  folds: 4

regimes:
  metric_key: exp
  buckets:
    - name: Weak
      max_exclusive: 0.65
    - name: Neutral
      min_inclusive: 0.65
      max_exclusive: 0.90
    - name: Strong
      min_inclusive: 0.90

policy_parameters:
  rolling_min_periods: 30

candidates:
  N0:
    is_control: true
    description: "control"
    type: constant
    value: 0.85
  A:
    description: "test candidate"
    type: constant
    value: 0.70

gates:
  - id: gate_1
    name: "test gate"
    expression: "cand.full.cagr > n0.full.cagr"

pbo:
  folds: 8
  min_configs_for_interpretation: 6

dsr:
  n_trials_source: 30

reporting:
  output_dir: reports
  report_name_template: "test_{date}.md"
  diagnostics_name_template: "test_{date}.csv"
"""


def _write_yaml(text: str) -> Path:
    """Write a temp YAML file (and companion trial_manifest.md so path validation succeeds) and return its path."""
    d = tempfile.mkdtemp(prefix="lab_test_")
    p = Path(d) / "test.yaml"
    p.write_text(text, encoding="utf-8")
    # Companion files that load_experiment_config resolves (not validated for existence but path is stored)
    (Path(d) / "preregistration.md").write_text("# test", encoding="utf-8")
    (Path(d) / "trial_manifest.md").write_text("cumulative_strategy_search: 30\n", encoding="utf-8")
    return p


def _replace(text: str, old: str, new: str) -> str:
    if old not in text:
        raise ValueError(f"old string not found in fixture: {old!r}")
    return text.replace(old, new, 1)


# ==================================== TESTS ====================================

# Test 1: missing required config field fails
def test_missing_required_field_raises():
    bad = _replace(_MINIMAL_YAML, "lab_id: LABTEST\n", "")
    with pytest.raises(LookupError, match="lab_id"):
        load_experiment_config(_write_yaml(bad))


# Test 2: duplicate YAML key fails
def test_duplicate_yaml_key_raises():
    bad = _MINIMAL_YAML + "\nlab_id: OVERWRITE\n"       # second top-level lab_id
    with pytest.raises(Exception, match="duplicate key"):
        load_experiment_config(_write_yaml(bad))


# Test 3: duplicate gate ID fails
def test_duplicate_gate_id_raises():
    bad = _replace(_MINIMAL_YAML,
                   'gates:\n  - id: gate_1\n    name: "test gate"\n    expression: "cand.full.cagr > n0.full.cagr"',
                   'gates:\n  - id: gate_1\n    name: "a"\n    expression: "cand.full.cagr > n0.full.cagr"\n'
                   '  - id: gate_1\n    name: "b"\n    expression: "cand.full.sharpe > n0.full.sharpe"')
    with pytest.raises(ValueError, match="duplicate gate id"):
        load_experiment_config(_write_yaml(bad))


# Test 4: zero/negative initial capital fails
def test_zero_initial_capital_raises():
    bad = _replace(_MINIMAL_YAML, "initial_capital: 100000", "initial_capital: 0")
    with pytest.raises(ValueError, match="initial_capital"):
        load_experiment_config(_write_yaml(bad))


# Test 5: canonical cost absent from grid fails
def test_canonical_cost_not_in_grid_raises():
    bad = _replace(_MINIMAL_YAML, "canonical_cost_bps: 15", "canonical_cost_bps: 99")
    with pytest.raises(ValueError, match="canonical_cost_bps"):
        load_experiment_config(_write_yaml(bad))


# Test 6: stress cost absent from grid fails
def test_stress_cost_not_in_grid_raises():
    bad = _replace(_MINIMAL_YAML, "promotion_stress_cost_bps: 50", "promotion_stress_cost_bps: 99")
    with pytest.raises(ValueError, match="promotion_stress_cost_bps"):
        load_experiment_config(_write_yaml(bad))


# Test 7: invalid period ordering fails
def test_period_ordering_raises():
    bad = _replace(_MINIMAL_YAML, 'discovery_end: "2023-10-13"',
                                    'discovery_end: "2025-01-01"')
    with pytest.raises(ValueError, match="discovery_end"):
        load_experiment_config(_write_yaml(bad))


# Test 8: odd/invalid PBO fold count fails
def test_odd_pbo_folds_raises():
    bad = _replace(_MINIMAL_YAML, "pbo:\n  folds: 8", "pbo:\n  folds: 7")
    with pytest.raises(ValueError, match="EVEN"):
        load_experiment_config(_write_yaml(bad))


# Test 9: overlapping regime buckets fail
def test_overlapping_regime_buckets_raises():
    bad = _replace(_MINIMAL_YAML,
                   "- name: Neutral\n      min_inclusive: 0.65\n      max_exclusive: 0.90",
                   "- name: Neutral\n      min_inclusive: 0.60\n      max_exclusive: 0.90")
    with pytest.raises(ValueError, match="overlap"):
        load_experiment_config(_write_yaml(bad))


# Test 10: invalid smooth taper range fails
def test_invalid_smooth_taper_raises():
    # Inject smooth-taper candidate INSIDE the candidates block with from_pctile > to_pctile
    inject = """  X:
    description: "bad taper"
    type: multiplicative_gates
    gates:
      india_vix:
        mode: smooth_taper
        window_days: 120
        from_pctile: 0.90
        to_pctile: 0.60
        multiplier_at_from_pctile: 1.0
        multiplier_at_to_pctile: 0.60
"""
    bad = _replace(_MINIMAL_YAML, "gates:\n  - id: gate_1", inject + "\ngates:\n  - id: gate_1")
    with pytest.raises(ValueError, match="from_pctile"):
        load_experiment_config(_write_yaml(bad))


# Test 11: unregistered policy fails loudly
def test_unregistered_policy_raises():
    with pytest.raises(KeyError, match="not registered"):
        R.get_policy_builder("NO_SUCH_POLICY_TYPE_12345")


# Test 12: unregistered simulator fails loudly
def test_unregistered_simulator_raises():
    with pytest.raises(KeyError, match="not registered"):
        R.get_simulator("NO_SUCH_SIMULATOR_67890")


# Test 13: AST evaluator accepts valid LAB007 expressions
def test_ast_accepts_valid_lab007_expressions():
    exprs = [
        "cand.conf.ulcer - n0.conf.ulcer >= 1.0",
        "((cand.conf.max_dd - n0.conf.max_dd) * 100 >= 3.0) or ((cand.conf.cvar5 - n0.conf.cvar5) * 100 >= 0.5)",
        "(cand.full.cagr - n0.full.cagr) * 100 >= -2.0",
        "cand.dsr.dsr > 0.90",
        "(cand_stress.conf.ulcer - n0_stress.conf.ulcer) >= 1.0",
    ]
    for e in exprs:
        compile_gate_expression(e, allowed_roots=("cand", "n0", "cand_stress", "n0_stress"))


# Test 14: AST evaluator rejects function calls
def test_ast_rejects_function_calls():
    with pytest.raises(SafeExpressionError, match="Disallowed"):
        compile_gate_expression("max(cand.full.cagr, n0.full.cagr) > 0",
                                 allowed_roots=("cand", "n0"))


# Test 15: AST evaluator rejects dunder access
def test_ast_rejects_dunder():
    with pytest.raises(SafeExpressionError, match="underscore"):
        compile_gate_expression("cand.__class__ == n0.__class__",
                                 allowed_roots=("cand", "n0"))


# Test 16: AST evaluator rejects arbitrary names (attribute access from non-whitelisted root)
def test_ast_rejects_bad_root_name():
    with pytest.raises(SafeExpressionError, match="not in allowed roots"):
        compile_gate_expression("os.pid > 0", allowed_roots=("cand", "n0"))


# Test 17: manifest parse-miss fails loudly (no silent fallback)
def test_manifest_parse_miss_raises():
    d = tempfile.mkdtemp(prefix="manifest_test_")
    p = Path(d) / "trial_manifest.md"
    p.write_text("this has no cumulative_strategy_search field", encoding="utf-8")
    with pytest.raises(LookupError, match="cumulative_strategy_search"):
        read_trial_manifest_count(p)


# ---------------- lightweight in-file runner if invoked directly ----------------
if __name__ == "__main__":
    import traceback
    tests = [(name, obj) for name, obj in list(globals().items()) if name.startswith("test_") and callable(obj)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}  ->  {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
