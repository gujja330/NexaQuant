"""Composite meta-ensemble · admission gate + conviction table."""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.recommendation.composite import compute_composite_score

_ROOT = Path(__file__).resolve().parents[2]


def test_r3_gets_zero_weight_when_trailing_n_below_50():
    r = compute_composite_score(
        runner_scores={"R1": 0.3, "R2": 0.4, "R3": 0.5},
        trailing_ic={"R1": 0.05, "R2": 0.08, "R3": 0.10},
        trailing_n={"R1": 100, "R2": 400, "R3": 30},
        root=_ROOT,
    )
    assert r["trust_weights_normalized"]["R3"] == 0.0
    assert r["admissions"]["R3"] == "NOT_ADMITTED"


def test_r3_admitted_when_trailing_n_ge_50():
    r = compute_composite_score(
        runner_scores={"R1": 0.3, "R2": 0.4, "R3": 0.5},
        trailing_ic={"R1": 0.05, "R2": 0.08, "R3": 0.10},
        trailing_n={"R1": 100, "R2": 400, "R3": 75},
        root=_ROOT,
    )
    assert r["admissions"]["R3"] == "ADMITTED"
    assert r["trust_weights_normalized"]["R3"] > 0.0


def test_all_three_agree_max_conviction():
    r = compute_composite_score(
        runner_scores={"R1": 0.5, "R2": 0.4, "R3": 0.3},
        trailing_ic={"R1": 0.05, "R2": 0.08, "R3": 0.10},
        trailing_n={"R1": 100, "R2": 400, "R3": 75},
        root=_ROOT,
    )
    assert r["conviction"] == "MAX_CONVICTION"


def test_conflict_2_of_3_watch_only():
    r = compute_composite_score(
        runner_scores={"R1": 0.5, "R2": -0.4, "R3": 0.3},   # R1+R3 buy · R2 sell
        trailing_ic={"R1": 0.05, "R2": 0.08, "R3": 0.10},
        trailing_n={"R1": 100, "R2": 400, "R3": 75},
        root=_ROOT,
    )
    assert r["conviction"] == "WATCH_ONLY_CONFLICT"


def test_only_r2_gives_existing_r2_sizing():
    r = compute_composite_score(
        runner_scores={"R1": 0.0, "R2": 0.4, "R3": 0.0},
        trailing_ic={"R1": 0.05, "R2": 0.08, "R3": 0.10},
        trailing_n={"R1": 100, "R2": 400, "R3": 75},
        root=_ROOT,
    )
    assert r["conviction"] == "EXISTING_R2_SIZING"


def test_all_silent_no_position():
    r = compute_composite_score(
        runner_scores={"R1": 0.0, "R2": 0.0, "R3": 0.0},
        trailing_ic={"R1": 0.05, "R2": 0.08, "R3": 0.10},
        trailing_n={"R1": 100, "R2": 400, "R3": 75},
        root=_ROOT,
    )
    assert r["conviction"] == "NO_POSITION"
