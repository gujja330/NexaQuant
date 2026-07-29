"""Guardrail: usa_daily orchestrator must not fail CI on optional-step failures.

The bug this locks in a fix for: prior code was
    return 0 if n_ok == len(STEPS) else 1
which meant ANY optional-step failure (e.g. rate-limited yfinance) killed
the whole pipeline exit code, even though `optional: True` is documented
as "failures do not abort the pipeline".

Verifies (via source inspection, not full pipeline execution):
 · Every optional step in STEPS carries `optional: True` and is exempt
   from the required-failure set
 · The final return statement uses `required_failures` (or an equivalent
   filter) rather than a raw `n_ok == len(STEPS)` comparison
 · The summary prints required + optional failure counts separately
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

USA_DAILY = _ROOT / "usa" / "scripts" / "usa_daily.py"


def _load_steps() -> list[dict]:
    tree = ast.parse(USA_DAILY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "STEPS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("STEPS constant not found in usa_daily.py")


def test_steps_constant_exists_and_has_entries():
    steps = _load_steps()
    assert len(steps) >= 10, "STEPS should have at least 10 pipeline steps"


def test_at_least_one_optional_step_declared():
    """If no step is optional we don't need the exit-code fix; if any is,
    the pipeline MUST not fail exit code on its failure."""
    steps = _load_steps()
    optionals = [s for s in steps if s.get("optional")]
    assert len(optionals) > 0, (
        "STEPS has no optional steps · either add optional flag to "
        "rate-limit-prone ingest steps OR remove the required_failures "
        "logic if truly nothing is optional."
    )


def test_exit_code_uses_required_failures_not_raw_n_ok():
    """Regression guardrail: the previous
        return 0 if n_ok == len(STEPS) else 1
    is banned. Must use a filter that excludes optional-step failures."""
    src = USA_DAILY.read_text(encoding="utf-8")
    banned = "return 0 if n_ok == len(STEPS) else 1"
    assert banned not in src, (
        f"BANNED exit-code pattern found: `{banned}` · this causes CI to "
        "fail on any optional step failure. Use `required_failures` instead."
    )
    # Positive check: fixed pattern present
    assert "required_failures" in src, (
        "usa_daily.py must partition results into required_failures + "
        "optional_failures and only exit 1 on required failures."
    )


def test_summary_prints_required_and_optional_counts_separately():
    """Operator visibility: summary must show what actually happened."""
    src = USA_DAILY.read_text(encoding="utf-8")
    assert "required failures" in src.lower()
    assert "optional failures" in src.lower()


def test_ledger_entry_records_partitioned_counts():
    """Ledger must record n_required_failure + n_optional_failure so
    audit can later distinguish 'we had bad data' from 'we broke prod'."""
    src = USA_DAILY.read_text(encoding="utf-8")
    assert "n_required_failure" in src
    assert "n_optional_failure" in src


def test_every_optional_flag_is_boolean_true():
    """Guard: `optional: True` must be exactly boolean, not truthy strings
    that would evaluate differently in edge cases."""
    steps = _load_steps()
    for s in steps:
        if "optional" in s:
            assert s["optional"] is True, (
                f"step {s['name']} has non-True optional={s['optional']!r}"
            )
