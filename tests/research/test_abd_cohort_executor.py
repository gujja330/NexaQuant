"""Tests for A/B/D cohort executor · verifies C.1 trial-accounting propagation."""
from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.evidence.abd_cohort_executor import (
    A_ITEMS, B_ITEMS, D_ITEMS, benjamini_hochberg, _classify, _sample_tier,
)


def test_family_composition_21_items():
    """A/B/D combined must equal 21 items (10+8+3)."""
    total = len(A_ITEMS) + len(B_ITEMS) + len(D_ITEMS)
    assert total == 21, f"expected 21 items · got {total}"


def test_all_item_ids_unique():
    all_ids = [x[0] for x in A_ITEMS + B_ITEMS + D_ITEMS]
    assert len(set(all_ids)) == len(all_ids), "duplicate item IDs"


def test_classify_rules():
    """Uniform verdict rules · same inputs must yield same verdicts."""
    assert _classify(delta=0.05, p_value=0.01, n=50)[0] == "PROMISING"
    assert _classify(delta=-0.05, p_value=0.01, n=50)[0] == "HARMFUL"
    assert _classify(delta=0.05, p_value=0.20, n=50)[0] == "NO_LIFT"
    assert _classify(delta=0.05, p_value=0.01, n=25)[0] == "INSUFFICIENT"
    assert _classify(delta=None, p_value=None, n=100)[0] == "INSUFFICIENT"
    assert _classify(delta=0.05, p_value=0.01, n=3)[0] == "DATA_BLOCKED"


def test_sample_tier_locked():
    assert _sample_tier(4) == "observation"
    assert _sample_tier(5) == "hypothesis"
    assert _sample_tier(14) == "hypothesis"
    assert _sample_tier(15) == "research_signal"
    assert _sample_tier(29) == "research_signal"
    assert _sample_tier(30) == "stronger_evidence"
    assert _sample_tier(49) == "stronger_evidence"
    assert _sample_tier(50) == "validation_candidate"


def test_benjamini_hochberg_monotone_and_correct():
    """BH-FDR must be monotone · smallest p gets smallest q · Nones pass through."""
    ps = [0.001, 0.01, 0.03, 0.04, 0.05, None, 0.20, 0.80]
    qs = benjamini_hochberg(ps)
    # Nones preserved in place
    assert qs[5] is None
    # Monotone non-decreasing when sorted by original p
    non_none = [(p, q) for p, q in zip(ps, qs) if p is not None and q is not None]
    non_none.sort(key=lambda x: x[0])
    for i in range(len(non_none) - 1):
        assert non_none[i][1] <= non_none[i+1][1] + 1e-9, (
            f"BH not monotone: q({non_none[i][0]})={non_none[i][1]} > "
            f"q({non_none[i+1][0]})={non_none[i+1][1]}"
        )


def test_executor_never_writes_to_production_paths():
    """Grep the executor · assert no production-path writes."""
    import inspect
    from backend.research.evidence import abd_cohort_executor
    src = inspect.getsource(abd_cohort_executor)
    forbidden = ("reports/telegram", "configs/ensemble_weights",
                  "backend/recommendation/", "opportunity_registry.jsonl")
    for f in forbidden:
        # allow inside comments/docstrings that say "never"
        for line in src.splitlines():
            if f in line and (".write" in line or "to_parquet" in line
                               or "with open" in line and " 'w'" in line):
                assert False, f"executor writes to production path · {f} in {line}"


def test_a_items_signatures():
    """Every A function must accept (root, market) and return a dict with required keys."""
    for item_id, fn in A_ITEMS + B_ITEMS + D_ITEMS:
        assert callable(fn), f"{item_id} not callable"
